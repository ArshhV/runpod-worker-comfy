# Docker Build Rules

## Platform Requirements

All Docker images in this project must be built with platform compatibility for RunPod.

### Required Platform Flag

When building Docker images for this project, always use the `--platform linux/amd64` flag to ensure compatibility with RunPod's infrastructure.

Example Docker build command:
```bash
docker build --platform linux/amd64 -t image-name:tag ./path/to/dockerfile
```

### Why This Matters

RunPod's infrastructure runs on x86_64 architecture. Building with the correct platform flag ensures:
- Proper compatibility with RunPod's servers
- Avoids architecture-related issues during deployment
- Consistent behavior across different environments

This rule applies to all Docker images in this project, including but not limited to:
- nariDia
- comfyUI
- deepseekVL
- Any future Docker images added to this project

### Standard Build Command Template

For any Docker image in this project, the build command should follow this pattern:
```bash
docker build --platform linux/amd64 -t [image-name]:[tag] ./[path-to-dockerfile-directory]
```