# ECS Timeout Troubleshooting Guide

## Problem Description

When running the Natural20 application in AWS ECS, you may encounter "Request timed out" errors when communicating with LLM providers, even though the same Docker image works fine locally.

## Root Cause

The issue is typically caused by:

1. **Missing or insufficient timeout configuration** - The original code had no explicit timeouts for OpenAI and insufficient timeouts for other providers
2. **Network latency in ECS** - ECS environments may have higher network latency than local development
3. **Security group or VPC configuration** - Incorrect network configuration can cause connectivity issues

## Solution Implemented

### 1. Added Configurable Timeouts

All LLM providers now support configurable timeouts via environment variables:

```bash
# Default timeouts (60 seconds each)
OPENAI_TIMEOUT=60
ANTHROPIC_TIMEOUT=60
OLLAMA_TIMEOUT=60

# Recommended for ECS (120 seconds each)
OPENAI_TIMEOUT=120
ANTHROPIC_TIMEOUT=120
OLLAMA_TIMEOUT=120
```

### 2. Fixed Missing Timeouts

- **OpenAI Provider**: Added explicit timeout parameter to API calls
- **Anthropic Provider**: Increased default timeout from 30s to 60s
- **Ollama Provider**: Increased default timeout from 30s to 60s

### 3. Enhanced Error Handling

Improved error messages and logging to help identify timeout issues.

## Configuration for ECS

### Environment Variables

Add these to your ECS task definition:

```json
{
  "environment": [
    {
      "name": "LLM_PROVIDER",
      "value": "openai"
    },
    {
      "name": "OPENAI_API_KEY",
      "value": "your-api-key"
    },
    {
      "name": "OPENAI_TIMEOUT",
      "value": "120"
    },
    {
      "name": "ANTHROPIC_TIMEOUT",
      "value": "120"
    },
    {
      "name": "OLLAMA_TIMEOUT",
      "value": "120"
    }
  ]
}
```

### Docker Configuration

When building your Docker image, you can set default timeouts:

```dockerfile
# Set default timeouts for ECS
ENV OPENAI_TIMEOUT=120
ENV ANTHROPIC_TIMEOUT=120
ENV OLLAMA_TIMEOUT=120
```

## Diagnostic Tools

### 1. ECS Timeout Diagnostic Script

Run the diagnostic script to identify network issues:

```bash
cd webapp
python diagnose_ecs_timeout.py
```

This script will:
- Test DNS resolution
- Test TCP connectivity
- Test HTTP endpoints
- Verify timeout configurations
- Provide specific recommendations

### 2. Timeout Configuration Test

Verify that timeout fixes are working:

```bash
cd webapp
python test_timeout_fix.py
```

## Troubleshooting Steps

### Step 1: Check Environment Variables

Verify that timeout environment variables are set correctly:

```bash
# Check current values
echo "OPENAI_TIMEOUT: $OPENAI_TIMEOUT"
echo "ANTHROPIC_TIMEOUT: $ANTHROPIC_TIMEOUT"
echo "OLLAMA_TIMEOUT: $OLLAMA_TIMEOUT"
```

### Step 2: Test Network Connectivity

Use the diagnostic script to test basic connectivity:

```bash
python diagnose_ecs_timeout.py
```

Look for:
- DNS resolution failures
- TCP connection failures
- HTTP timeout errors

### Step 3: Check ECS Security Groups

Ensure your ECS task has the correct outbound rules:

```
Type: All traffic
Protocol: All
Port: All
Destination: 0.0.0.0/0
```

### Step 4: Check VPC Configuration

If using a VPC:

1. **Public Subnets**: Ensure they have an Internet Gateway attached
2. **Private Subnets**: Ensure they have a NAT Gateway configured
3. **Route Tables**: Verify routes are configured correctly

### Step 5: Monitor Application Logs

Look for these timeout-related errors in your application logs:

```
ERROR: Error sending message to OpenAI: Request timed out
ERROR: Error sending message to Anthropic: Request timed out
ERROR: Error sending message to Ollama: Request timed out
```

### Step 6: Test with Different Providers

Try switching between different LLM providers to isolate the issue:

```bash
# Test OpenAI
export LLM_PROVIDER=openai
export OPENAI_TIMEOUT=120

# Test Anthropic
export LLM_PROVIDER=anthropic
export ANTHROPIC_TIMEOUT=120

# Test Ollama
export LLM_PROVIDER=ollama
export OLLAMA_TIMEOUT=120
```

## Common Issues and Solutions

### Issue 1: "Request timed out" with OpenAI

**Symptoms:**
- Works locally but fails in ECS
- No specific error message beyond timeout

**Solutions:**
1. Increase `OPENAI_TIMEOUT` to 120-180 seconds
2. Check if using a custom `OPENAI_BASE_URL` (may have different latency)
3. Verify API key is valid and has sufficient credits

### Issue 2: "Request timed out" with Anthropic

**Symptoms:**
- Similar to OpenAI but with Anthropic API

**Solutions:**
1. Increase `ANTHROPIC_TIMEOUT` to 120-180 seconds
2. Check API key validity
3. Verify account has sufficient credits

### Issue 3: "Request timed out" with Ollama

**Symptoms:**
- Fails to connect to Ollama instance
- May indicate network connectivity issues

**Solutions:**
1. Increase `OLLAMA_TIMEOUT` to 120-180 seconds
2. Verify Ollama is running and accessible
3. Check `OLLAMA_BASE_URL` configuration
4. Ensure Ollama instance has sufficient resources

### Issue 4: Intermittent Timeouts

**Symptoms:**
- Sometimes works, sometimes fails
- No consistent pattern

**Solutions:**
1. Increase all timeout values significantly (180-300 seconds)
2. Check for resource constraints in ECS task
3. Monitor CPU and memory usage
4. Consider using larger ECS task sizes

## Performance Optimization

### 1. Use VPC Endpoints

For better performance, consider using VPC endpoints:

- **OpenAI**: Use a VPC endpoint for API Gateway
- **Anthropic**: Use a VPC endpoint for API Gateway

### 2. Optimize Model Selection

- Use smaller/faster models when possible
- Consider model response times in your choice

### 3. Implement Retry Logic

Consider implementing retry logic in your application for transient failures.

## Monitoring and Alerting

### 1. CloudWatch Metrics

Monitor these metrics in CloudWatch:
- ECS task CPU and memory usage
- Network I/O
- Application error rates

### 2. Application Logs

Set up log aggregation to monitor:
- Timeout error frequency
- Response time patterns
- Provider-specific issues

### 3. Health Checks

Implement health checks that test LLM connectivity:
- Regular ping tests to LLM providers
- Response time monitoring
- Error rate tracking

## Best Practices

### 1. Start with Conservative Timeouts

Begin with higher timeout values (120-180 seconds) and adjust based on performance.

### 2. Monitor and Adjust

Regularly monitor timeout performance and adjust values as needed.

### 3. Use Environment-Specific Configurations

Use different timeout values for different environments:
- Development: 60 seconds
- Staging: 90 seconds
- Production: 120-180 seconds

### 4. Document Changes

Keep track of timeout changes and their impact on performance.

## Support

If you continue to experience issues after implementing these solutions:

1. Run the diagnostic script and share the output
2. Check ECS task logs for detailed error messages
3. Verify your network configuration
4. Consider testing with a different LLM provider

## Files Modified

- `webapp/llm_handler.py` - Added timeout configuration
- `webapp/env.example` - Added timeout environment variables
- `Dockerfile` - Added timeout documentation
- `webapp/LLM_CONFIGURATION.md` - Added timeout configuration guide
- `webapp/diagnose_ecs_timeout.py` - New diagnostic script
- `webapp/test_timeout_fix.py` - New test script
- `webapp/ECS_TIMEOUT_TROUBLESHOOTING.md` - This troubleshooting guide 