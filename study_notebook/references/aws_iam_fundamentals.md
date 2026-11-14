# AWS IAM Fundamentals for Beginners

## Core Concepts
1. **IAM User**: An identity with long-term credentials for a specific person or application.
2. **IAM Role**: An identity with temporary security credentials. Used by EC2 instances, Lambda, or cross-account access.
3. **IAM Policy**: A JSON document defining permissions (Allow or Deny) on specific AWS resources.

## Principle of Least Privilege
Always grant only the minimum permissions necessary to perform a task. 
Never use wildcard actions like 's3:*' or unrestricted resources '*' in production policies.
