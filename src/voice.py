import os
import tempfile
import asyncio
import ctypes
import subprocess
import threading
import time
import msvcrt
import winreg
import edge_tts
from typing import Optional

DEFAULT_VOICE = "en-US-AvaNeural"

# ---------------------------------------------------------------------------
# Audio Playback Device Auto-Detection (Headphones vs Speakers)
# ---------------------------------------------------------------------------

_PS_DEVICE_CODE = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice {
    int Activate(ref Guid id, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object interfacePointer);
    int OpenPropertyStore(int stgmAccess, out IntPtr properties);
    int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
    int GetState(out int state);
}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
public class MMDeviceEnumeratorComObject { }
public class AudioUtil {
    public static string GetDefaultPlaybackDeviceId() {
        try {
            var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
            IMMDevice dev;
            enumerator.GetDefaultAudioEndpoint(0, 0, out dev);
            string id;
            dev.GetId(out id);
            return id;
        } catch { return ""; }
    }
}
'@
[AudioUtil]::GetDefaultPlaybackDeviceId()
"""

_CACHED_DEVICE = None
_CACHED_TIME = 0.0

def detect_audio_playback_device(force_refresh: bool = False) -> tuple[bool, str]:
    """
    Detects the current Windows default audio output endpoint and determines
    whether the user is listening through headphones/headset vs external speakers.

    Returns:
        (is_headphones: bool, device_description: str)
    """
    global _CACHED_DEVICE, _CACHED_TIME
    now = time.time()
    if not force_refresh and _CACHED_DEVICE and (now - _CACHED_TIME < 15.0):
        return _CACHED_DEVICE

    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(_PS_DEVICE_CODE)
            tmp = f.name

        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
            capture_output=True, text=True, timeout=5
        )
        dev_id = r.stdout.strip()
        if "{" in dev_id and "}" in dev_id:
            guid = dev_id.split(".")[-1]
            key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render\{guid}\Properties"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                d = {}
                for i in range(winreg.QueryInfoKey(k)[1]):
                    n, v, t = winreg.EnumValue(k, i)
                    d[n] = v

                type_name = str(d.get("{a45c254e-df1c-4efd-8020-67d146a850e0},2", "Audio Device"))
                friendly = str(d.get("{b3f8fa53-0004-438e-9003-51a46e139bfc},6", ""))
                disp = f"{type_name} ({friendly})" if friendly else type_name

                combined = (type_name + " " + friendly + " " + " ".join(str(x) for x in d.values() if isinstance(x, str))).lower()
                headphone_keywords = [
                    "headphone", "headset", "earphone", "buds", "airpod",
                    "lightspeed", "wireless mode", "iem", "wh-1000", "qc35", "qc45"
                ]
                is_hp = any(hk in combined for hk in headphone_keywords)
                _CACHED_DEVICE = (is_hp, disp)
                _CACHED_TIME = now
                return _CACHED_DEVICE
    except Exception:
        pass
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

    _CACHED_DEVICE = (False, "Speakers")
    _CACHED_TIME = now
    return _CACHED_DEVICE

# ---------------------------------------------------------------------------
# Speech-to-Text (STT) — Windows System.Speech, zero extra installs
# ---------------------------------------------------------------------------

_PS1_STT_TEMPLATE = r"""
Add-Type -AssemblyName System.Speech
$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$rec.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$rec.LoadGrammar($grammar)

# Prevent premature cut-offs during natural pauses & breaths
$rec.InitialSilenceTimeout = [TimeSpan]::FromSeconds({initial_silence})
$rec.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.8)
$rec.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromSeconds(2.2)
$rec.BabbleTimeout = [TimeSpan]::FromSeconds(4)

$phrases = [System.Collections.Generic.List[string]]::new()
$startTime = [DateTime]::UtcNow
$maxDuration = [TimeSpan]::FromSeconds({total_timeout})

try {{
    while (([DateTime]::UtcNow - $startTime) -lt $maxDuration) {{
        # Once speech has started, allow up to 3.0s of silence between clauses before finalizing
        $listenWindow = if ($phrases.Count -gt 0) {{ [TimeSpan]::FromSeconds(3) }} else {{ [TimeSpan]::FromSeconds({initial_silence}) }}
        
        $res = $rec.Recognize($listenWindow)
        if ($res -ne $null -and $res.Text -ne '') {{
            $phrases.Add($res.Text.Trim())
        }} else {{
            # Silence reached -> utterance complete
            break
        }}
    }}
}} catch {{
    # Exit gracefully on interrupt or device release
}} finally {{
    $rec.Dispose()
}}

if ($phrases.Count -gt 0) {{
    Write-Output ($phrases -join ' ')
}} else {{
    Write-Output 'NO_SPEECH'
}}
"""

def listen(timeout_seconds: int = 15, beep: bool = True) -> Optional[str]:
    """
    Records from the default microphone and returns transcribed text, or None on silence/error.

    Uses Windows built-in System.Speech.Recognition.SpeechRecognitionEngine via a
    temporary PowerShell .ps1 file (zero extra Python packages required).

    Features:
        - Multi-clause phrase accumulation (won't cut off when pausing between words/clauses).
        - Generous EndSilenceTimeout (1.8s) so natural speech breaths don't interrupt recognition.
        - Audio cue chime (*BEEP*) when the microphone is live.

    Parameters:
        timeout_seconds: Target wait time (default: 15 seconds).
        beep: Play a short cue chime when the microphone opens.

    Returns:
        str  — transcribed speech text (full concatenated utterance)
        None — if no speech detected, timeout, or microphone not available
    """
    initial_silence = max(8, timeout_seconds - 5)
    total_timeout   = timeout_seconds + 10          # hard wall-clock limit (e.g. 25s)

    # Short auditory cue that mic is open
    if beep:
        try:
            import winsound
            winsound.Beep(880, 100)
        except Exception:
            pass

    ps1_script = _PS1_STT_TEMPLATE.format(
        initial_silence=initial_silence,
        total_timeout=total_timeout
    )

    tmp_ps1 = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False, encoding="utf-8"
        ) as f:
            f.write(ps1_script)
            tmp_ps1 = f.name

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-File", tmp_ps1,
            ],
            capture_output=True,
            text=True,
            timeout=total_timeout + 6,   # allow PowerShell clean exit
        )
        stdout = result.stdout.strip()

        # Ignore any PowerShell noise lines (warnings, blank lines)
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            if line == "NO_SPEECH":
                return None
            # Non-empty, non-error line → that's the transcript
            return line

        return None

    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        # powershell.exe not on PATH
        return None
    except Exception:
        return None
    finally:
        if tmp_ps1 and os.path.exists(tmp_ps1):
            try:
                os.remove(tmp_ps1)
            except Exception:
                pass

def _play_interruptible(audio_path: str, stop_event: threading.Event) -> str:
    """
    Plays an MP3 file using native Windows MCI in an interruptible loop.
    Allows immediate termination by keypress (msvcrt.kbhit) or stop_event.
    Returns: 'FINISHED' or 'INTERRUPTED'
    """
    winmm = ctypes.windll.winmm
    alias = f"mentor_speech_{os.getpid()}"
    winmm.mciSendStringW(f"close {alias}", None, 0, 0)
    winmm.mciSendStringW(f'open "{audio_path}" type mpegvideo alias {alias}', None, 0, 0)
    winmm.mciSendStringW(f"play {alias}", None, 0, 0)

    buf = ctypes.create_unicode_buffer(64)
    reason = "FINISHED"
    try:
        while not stop_event.is_set():
            # Option 1: Tap any key / Enter to cut off audio immediately
            if msvcrt.kbhit():
                msvcrt.getch()  # consume keypress
                reason = "INTERRUPTED"
                stop_event.set()
                print("\n[Playback cut off by keypress]")
                break
            winmm.mciSendStringW(f"status {alias} mode", buf, 64, 0)
            if buf.value != "playing":
                reason = "FINISHED"
                break
            time.sleep(0.04)
    finally:
        winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
        winmm.mciSendStringW(f"close {alias}", None, 0, 0)
    return reason

def _play_with_sapi_fallback(text: str):
    """Offline fallback using Windows built-in System.Speech synthesizer."""
    escaped = text.replace("'", "''").replace('"', '`"')
    ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def speak_with_bargein(text: str, is_headphones: Optional[bool] = None, voice: str = DEFAULT_VOICE) -> Optional[str]:
    """
    Speaks text hands-free with dual-mode barge-in:
      - Option 1 (All Devices): Tap [Enter] or any key to cut off speech instantly.
      - Option 2 (Headphones Only): Live Voice Barge-In. Speaking into the headset mic
        instantly cuts off the audio and returns your transcribed speech!

    Returns:
        str  — Transcribed voice interruption (if interrupted by voice)
        None — If finished normally or interrupted by keypress
    """
    if not text or not text.strip():
        return None

    if is_headphones is None:
        is_headphones, dev_name = detect_audio_playback_device()
    else:
        dev_name = "Headphones" if is_headphones else "Speakers"

    # Strip markdown syntax for natural speech
    clean_text = text.replace("```", "").replace("*", "").replace("#", "").replace("[", "").replace("]", "")
    if len(clean_text) > 800:
        clean_text = clean_text[:800] + "... and more."

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        temp_audio = f.name

    try:
        comm = edge_tts.Communicate(clean_text, voice)
        asyncio.run(comm.save(temp_audio))
    except Exception:
        # Fall back to native Windows offline speech synthesis
        _play_with_sapi_fallback(clean_text)
        return None

    stop_event = threading.Event()
    voice_interruption_result = [None]

    try:
        if is_headphones:
            print(f"[🎧 Active: {dev_name} | Tap Enter or SPEAK to interrupt]")

            # Function to listen for voice interruption in parallel
            def _voice_listener():
                # Listen without beep so we don't disrupt speech playback
                heard = listen(timeout_seconds=20, beep=False)
                if heard:
                    voice_interruption_result[0] = heard
                    stop_event.set()
                    # Stop MCI playback immediately
                    winmm = ctypes.windll.winmm
                    alias = f"mentor_speech_{os.getpid()}"
                    winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
                    winmm.mciSendStringW(f"close {alias}", None, 0, 0)

            listener_thread = threading.Thread(target=_voice_listener, daemon=True)
            listener_thread.start()

            # Play audio in foreground
            _play_interruptible(temp_audio, stop_event)

            # If voice interruption occurred:
            if voice_interruption_result[0]:
                print(f"[🎤 Voice Interrupted!]")
                return voice_interruption_result[0]

        else:
            # External speakers: Option 1 only (keyboard tap) to prevent feedback loops
            print(f"[🔊 Active: {dev_name} | Tap Enter to interrupt audio]")
            _play_interruptible(temp_audio, stop_event)

    finally:
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except Exception:
                pass

    return None

def speak(text: str, voice: str = DEFAULT_VOICE) -> Optional[str]:
    """Unified speak interface with auto-detected barge-in."""
    return speak_with_bargein(text, voice=voice)
