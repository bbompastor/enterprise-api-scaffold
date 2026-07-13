# Enterprise API — Infrastructure Scaffold

A lightweight deployment template demonstrating how I structure Kubernetes workloads for a production Python service. Built to mirror patterns common in platform teams: **GitHub Actions → GHCR → Helm deploy → Istio service mesh → Prometheus observability**.

This is intentionally small (a few hours of work) but opinionated — the kind of scaffold I'd hand to an application team on day one.

## What's in here

```
.
├── api/                      # Minimal Python HTTP service (health, readiness, metrics)
├── tests/                    # Unit tests (stdlib unittest)
├── helm/
│   └── api/                  # Helm chart for packaging and deployment
│       ├── templates/        # Kubernetes manifests templates (PDB, HPA, Istio, etc.)
│       ├── values.yaml       # Default chart values
│       ├── values-dev.yaml   # Environment overrides for Dev
│       └── values-prod.yaml  # Environment overrides for Prod
├── .github/workflows/
│   └── ci-cd.yml             # Test → build → deploy to k8s
├── Dockerfile                # Slim Python image, non-root
└── requirements.txt          # No runtime deps (stdlib only)
```

## Design Decisions & Architecture

### Kubernetes structure

- **Helm Chart packaging** (`helm/api`) with environment-specific values files (`values-dev.yaml` and `values-prod.yaml`) to eliminate duplicate manifests and maintain clean parameterization.
- **PodDisruptionBudget** (`minAvailable: 1`) so node drains and cluster upgrades don't take the service fully offline.
- **Topology spread + pod anti-affinity** to spread replicas across AZs and nodes.
- **HPA** on CPU (70% target) with different min/max per environment via Helm values overrides.
- **Security defaults**: non-root container, read-only root FS, dropped capabilities, slim base image.

### Istio (service mesh)

- **Gateway** terminates TLS at the ingress.
- **VirtualService** sets timeouts (10s) and retries (3 attempts, retry on 5xx/connection failures).
- **DestinationRule** configures connection pooling, outlier detection (circuit breaking), and `LEAST_REQUEST` load balancing.

These are the knobs I'd reach for before adding application-level retry logic.

### CI/CD for Kubernetes (GitHub Actions)

The pipeline in `.github/workflows/ci-cd.yml` handles the full lifecycle:

| Trigger | Jobs |
|---------|------|
| Pull request | `test`, `validate-chart` |
| Push to `develop` | Above + `build-and-push` → `deploy-dev` |
| Push to `main` | Above + `build-and-push` → `deploy-prod` (matrix: `us-east-1`, `eu-west-1`) |

**Flow:**

```
PR → unit tests + helm lint and template validation
main/develop → build image → push to GHCR → helm upgrade --install (with values overrides)
```

**Why GitHub Actions over a GitOps controller?**

For a small team or a single service, pipeline-driven deploys are simpler to reason about — one tool, one audit trail, no extra cluster component. The trade-off is you lose continuous drift reconciliation (ArgoCD's `selfHeal`), so I mitigate that by:

- Immutable image tags (git SHA) set at deploy time
- Helm release verification (`--wait --timeout 5m`) to gate the pipeline on success
- GitHub **environments** (`production`, `development`) for approval gates and scoped secrets

For larger platforms with many services, I'd still reach for ArgoCD or Flux — but GitHub Actions is a pragmatic default when the team already lives in GitHub.

**Required secrets:**

| Secret | Purpose |
|--------|---------|
| `KUBECONFIG_US_EAST_1` | Base64-encoded kubeconfig for prod (us-east-1) |
| `KUBECONFIG_EU_WEST_1` | Base64-encoded kubeconfig for prod (eu-west-1) |
| `KUBECONFIG_DEV` | Base64-encoded kubeconfig for dev cluster |

`GITHUB_TOKEN` is used automatically for GHCR push.

### Multi-region / high availability

`deploy-prod` uses a **matrix strategy** to roll out the same prod Helm configuration to `us-east-1` and `eu-west-1` in parallel.

At the platform level, HA for a stateless API like this is mostly:

1. **≥3 replicas per region** (prod values) across ≥2 AZs.
2. **Global load balancing** (Route 53 latency/failover, or CloudFront + ALB) in front of regional Istio gateways.
3. **Health-checked failover** — `/healthz` returns region metadata so you can verify routing during game days.
4. **PDB + rolling updates** (`maxUnavailable: 0`) so deploys never drop below quorum.

### Observability

- Prometheus **ServiceMonitor** scrapes `/metrics` every 30s.
- Pod annotations as a fallback for clusters without the Prometheus Operator.
- In production I'd add: RED metrics (rate, errors, duration) via Istio telemetry, structured logs to a central sink, and SLO-based alerting (e.g. burn-rate on error budget).

## Quick start (local validation)

```bash
# Build and run the service
python -m api.main
curl localhost:8080/healthz

# Run tests
python -m unittest discover -s tests -v

# Validate Helm chart linting and templates locally
helm lint helm/api -f helm/api/values.yaml -f helm/api/values-dev.yaml
helm template dev-api helm/api -f helm/api/values.yaml -f helm/api/values-dev.yaml

# Build container
docker build -t api:local .
```

## What I'd extend in a real engagement

- NetworkPolicies restricting ingress to the Istio sidecar only
- ExternalSecrets for TLS certs and DB credentials
- Canary deploys via Istio traffic splitting (90/10 → 50/50 → 100)
- OPA/Gatekeeper policies enforcing labels, resource limits, and `runAsNonRoot`
- OIDC federation for kubeconfig-less cluster auth (e.g. AWS EKS `aws eks get-token`)

---

## Local Runbook (Local Setup & Verification)

Use these commands to manage your local testing infrastructure on macOS.

### 1. Suspend & Resume (Recommended)
This pauses Colima and shuts down port-forwarding, saving CPU/RAM without deleting any configs or pods.

#### Stop Everything:
```bash
# Stop background port-forwarding processes
killall kubectl

# Suspend the Colima VM (automatically pauses your Kind cluster)
colima stop
```

#### Start/Resume Everything:
```bash
# Resume Colima VM
colima start

# Wait a few seconds, then verify the pods are healthy
kubectl get pods -n enterprise-api

# Start port-forwarding in the background
kubectl port-forward service/dev-api -n enterprise-api 8080:80 &

# Verify the service responds correctly
curl http://localhost:8080/healthz
```

> [!TIP]
> **Troubleshooting Colima Resume Issues:**
> 1. **`Forbidden: User "kubernetes-admin" cannot list...`**: This happens if you run `kubectl` commands immediately after `colima start`. The cluster API server takes 10–15 seconds to fully initialize RBAC. Wait a few seconds and run the command again.
> 2. **Pod in `Unknown` status**: Since the container runtime was paused and resumed, the pod's container sandbox might need a restart. If the pod stays in `Unknown` or does not transition to `Running`, delete it to force Kubernetes to recreate it:
>    ```bash
>    kubectl delete pod -n enterprise-api -l app.kubernetes.io/name=api --force --grace-period=0
>    ```


### 2. Full Clean & Recreate (Start from Scratch)
Use this if you want to completely destroy and recreate the cluster.

#### Delete Cluster:
```bash
killall kubectl
kind delete cluster --name synthesia-test
colima stop
```

#### Rebuild Cluster:
```bash
# 1. Start Docker runtime
colima start

# 2. Spin up cluster & load local image
kind create cluster --name synthesia-test
docker build -t api:local .
kind load docker-image api:local --name synthesia-test

# 3. Deploy Prometheus stack (installs CRDs)
helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace

# 4. Install Istio control plane & enable injection
istioctl install --set profile=demo -y
kubectl label namespace enterprise-api istio-injection=enabled --overwrite

# 5. Deploy Helm Chart (with Istio & ServiceMonitor enabled)
helm upgrade --install dev-api helm/api \
  -f helm/api/values.yaml \
  -f helm/api/values-dev.yaml \
  --namespace enterprise-api \
  --create-namespace \
  --set image.repository="api" \
  --set image.tag="local" \
  --set image.pullPolicy="IfNotPresent" \
  --set istio.enabled=true \
  --set serviceMonitor.enabled=true

# 6. Recreate pod to trigger Istio injection
kubectl delete pod -n enterprise-api -l app.kubernetes.io/name=api

# 7. Start port-forwarding & query
kubectl port-forward service/dev-api -n enterprise-api 8080:80 &
curl http://localhost:8080/healthz
```


