# Kubernetes Staging Layout

This folder stages TheAssembly app workloads and Docker MCP workloads as separate Kubernetes deployments with hardened networking and multi-environment overlays for **development and staging environments only**.

## 🚀 Deployment Model

**Production**: Streamlit Cloud (primary)
- `asm-athlete.streamlit.app`
- `asm-control.streamlit.app`
- These URLs remain unchanged and unaffected by K8s infrastructure

**Staging & Development**: Self-hosted Kubernetes (this folder)
- **Staging**: `stage-asm-athlete.theassembly.app`, `stage-asm-control.theassembly.app` (public via Traefik Ingress)
- **Development**: Internal service discovery (no public Ingress)

This setup enables testing infrastructure changes and MCP services before deciding on a future full self-hosted production deployment.

## Separation Model

- App workloads: `theassembly-apps` namespace
  - `athlete`
  - `admin`
- MCP workloads: `theassembly-mcp` namespace
  - `mcp-playwright`
  - `mcp-pyright` (containerized Python analysis alternative)

`Pylance` is a VS Code extension and stays on the developer/editor side; it is not deployed as an MCP server.

## Base Manifests

The `base/` directory contains:
- **Namespaces**: `namespace-apps.yaml`, `namespace-mcp.yaml` with isolation labels
- **Deployments**: Athlete, admin, playwright MCP, pyright MCP with resource limits and health checks
- **Shared Config**: `shared-configmap.yaml` for common environment variables
- **Secrets Template**: `app-secret-template.yaml` (requires user-provided values)
- **Network Policies**: 
  - `networkpolicy-apps-default-deny.yaml`: Default deny all ingress/egress in apps namespace
  - `networkpolicy-mcp-default-deny.yaml`: Default deny all ingress/egress in MCP namespace
  - `networkpolicy-allow-rules.yaml`: Explicit allow rules for app→MCP (ports 8931, 8932), ingress→apps (8501), DNS, and external egress
- **Ingress** (staging only): 
  - `ingress-stage.yaml`: Traefik Ingress for stage hostnames (stage-asm-athlete.theassembly.app, stage-asm-control.theassembly.app) with TLS via cert-manager

Apply base manifests:

```bash
kubectl apply -k deploy/k8s/base
```

## Environment Overlays

Deploy environment-specific configurations using Kustomize overlays:

### Dev Overlay

Development environment: single replicas, no public Ingress, resource-efficient.

```bash
kubectl apply -k deploy/k8s/overlays/dev
```

### Stage Overlay

Staging environment: 2 replicas for apps and playwright MCP, 1 replica for pyright MCP, public Ingress with TLS on stage hostnames.

```bash
kubectl apply -k deploy/k8s/overlays/stage
```

### Prod Overlay (Template for Future Use)

**NOTE**: Production currently remains on Streamlit Cloud (`asm-athlete.streamlit.app`, `asm-control.streamlit.app`). 

The `overlays/prod` directory is provided as a **template for eventual full self-hosting** if you decide to migrate off Streamlit Cloud in the future. It includes:
- 3 replicas for apps and playwright MCP, 2 replicas for pyright MCP
- Streamlit memory limits increased to **1Gi** for athlete/admin (prevents OOMKill during peak load)
- Public Ingress with TLS on prod hostnames (asm-athlete.theassembly.app, asm-control.theassembly.app)

**To activate prod overlay** (requires DNS migration from streamlit.app to your K8s cluster):

```bash
kubectl apply -k deploy/k8s/overlays/prod
```

**Prod memory tuning** (when activated):
- Athlete/admin requests: 768Mi, limits: 1Gi (enforced by K8s; exceeding will trigger OOMKill)
- MCP playwright requests: 512Mi, limits: 1Gi
- MCP pyright requests: 256Mi, limits: 512Mi

## Required edits before deployment

### For Dev and Stage environments:

1. **Image references**: Replace in base manifests:
   - `ghcr.io/your-org/theassembly:latest` → your athlete/admin image
   - `ghcr.io/your-org/mcp-playwright:latest` → your playwright MCP image
   - `ghcr.io/your-org/mcp-pyright:latest` → your pyright MCP image

2. **Secrets**: Edit `app-secret-template.yaml`:
   - GitHub token (for TheAssembly repo and dependency access)
   - Admin password for admin app
   - Other sensitive config (recommendations: use Sealed Secrets or External Secrets Operator)

3. **TLS Prerequisites** (stage environment only):
   - Install cert-manager v1.13.0:
     - `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml`
   - Apply staging ClusterIssuer from repo bootstrap:
     - `kubectl apply -f deploy/k8s/bootstrap/clusterissuer-letsencrypt-staging.yaml`
   - Verify issuer readiness:
     - `kubectl get clusterissuer letsencrypt-staging`

4. **Ingress Controller** (stage environment only):
   - Install Traefik from repo bootstrap:
     - `kubectl apply -f deploy/k8s/bootstrap/traefik-install.yaml`
   - Verify IngressClass:
     - `kubectl get ingressclass traefik`
   - Verify service exposure:
     - `kubectl get svc -n traefik traefik`

5. **Local cluster TLS note**:
   - Let's Encrypt HTTP-01 requires publicly reachable DNS/HTTP endpoints.
   - On local Docker Desktop/Minikube, certificates may remain `pending` unless domains resolve publicly to your cluster.
   - For local-only testing, use port-forward with HTTP (`kubectl -n traefik port-forward svc/traefik 8080:80`) or use a local CA/self-signed cert instead of Let's Encrypt.

6. **Network Policy Validation**:
   - Confirm NetworkPolicies are active: `kubectl get networkpolicies -n theassembly-apps`
   - Test app→MCP access: `kubectl run -it --rm test --image=busybox -- wget -O- http://mcp-playwright:8931` (from athlete pod)
   - Test external→app access: `kubectl logs -f svc/athlete -n theassembly-apps` to verify ingress routing

### For Production (when ready to migrate from Streamlit Cloud):

Follow the same steps above, then:
1. Update DNS records to point `asm-athlete.theassembly.app` and `asm-control.theassembly.app` to your K8s Ingress load balancer IP
2. Activate prod overlay: `kubectl apply -k deploy/k8s/overlays/prod`
3. Monitor Streamlit memory usage; confirm athlete/admin pods show 1Gi limit via `kubectl describe pod`

## Optional local Docker profile for MCP services

Use the extra compose file to run MCP services separately from app containers:

```bash
docker compose -f docker-compose.yml -f docker-compose.mcp.yml --profile mcp up -d
```

This keeps athlete/admin startup behavior unchanged while enabling separate MCP container lifecycles.

