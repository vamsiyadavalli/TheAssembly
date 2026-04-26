# Setup: Docker Desktop Kubernetes & Local K8s Deployment

## Step 1: Enable Kubernetes in Docker Desktop

1. Open **Docker Desktop** on your Mac
2. Click the **Docker icon** in the menu bar → **Preferences**
3. Go to **Kubernetes** tab
4. Check ✓ **Enable Kubernetes**
5. Click **Apply & Restart** (this will take a few minutes)
6. Wait for Docker Desktop to restart and Kubernetes to start

## Step 2: Verify Kubernetes is Running

```bash
kubectl cluster-info
kubectl get nodes
```

Expected output:
```
Kubernetes control plane is running at https://kubernetes.docker.internal:6443
...
NAME             STATUS   ROLES           AGE   VERSION
docker-desktop   Ready    control-plane   1m    v1.28.0
```

## Step 3: Create a namespace for testing (optional)

```bash
kubectl create namespace test
kubectl get namespaces
```

## Step 4: Proceed with cert-manager Installation

Once Docker Desktop shows `STATUS Ready`, run:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=300s
```

## Troubleshooting

### Docker Desktop shows "kubernetes-cli" error
- **Cause**: kubectl not installed or not in PATH
- **Fix**: Install Docker Desktop again (includes kubectl) or install kubectl separately: `brew install kubectl`

### Kubernetes won't start or shows "Restarting"
- **Cause**: Insufficient resources or Docker daemon issue
- **Fix**: 
  - Ensure Docker Desktop has at least 4GB RAM allocated (Preferences → Resources)
  - Restart Docker Desktop completely
  - Check system storage (need ~5GB free space)

### "connection refused" after enabling Kubernetes
- **Cause**: Kubernetes still initializing
- **Fix**: Wait 30-60 seconds, then retry `kubectl cluster-info`

---

Once Kubernetes is verified running, return to implement cert-manager and Traefik installation.
