# deploy/k8s/

Kubernetes manifests for the API service. Hardened pod spec with readOnlyRootFilesystem, runAsNonRoot, capability drop, and readiness/liveness probes on the monitoring endpoints.

## Files

| File | Purpose |
|------|---------|
| `deployment.yaml` | `Deployment` (2 replicas) + `Service` (port 80 → container 8000). Non-root uid 1000, fsGroup 1000, drops all Linux capabilities, mounts `cashflow-db` + `cashflow-auth` as env secrets. |

## Run individually

### Pre-requisites
- A reachable cluster (`kubectl config current-context`).
- Image pushed to a registry your cluster can pull from (`cashflow/api:latest` is a placeholder).
- Secrets created:

```bash
kubectl create secret generic cashflow-db \
    --from-literal=url='postgresql+psycopg://user:pass@host:5432/cashflow'

kubectl create secret generic cashflow-auth \
    --from-literal=signing_key='change-me-prod-value'

kubectl create secret generic cashflow-data-hub \
    --from-literal=signing_key='shared-with-data-hub-team'
```

### Apply
```bash
kubectl apply -f deploy/k8s/deployment.yaml
kubectl get pods -l app=cashflow
kubectl port-forward svc/cashflow-api 8000:80
```

### Tear down
```bash
kubectl delete -f deploy/k8s/deployment.yaml
```

## Role in orchestration pipeline

These manifests run the API + (via CronJob, not yet in this folder) the scheduled `orchestrator.scheduler` pipeline run. The DAG itself is the same code as in dev — only the runtime environment differs.

## What to add next when productionising

- `CronJob` resource for the nightly `python -m orchestrator.scheduler` batch run.
- `ConfigMap` holding `config.yml` so operators can tweak KPI weights without a rebuild.
- `HorizontalPodAutoscaler` on the API once traffic grows.
- `NetworkPolicy` restricting outbound traffic to the Data Hub's IP range.
- `PodDisruptionBudget` so rolling updates don't take the last replica down.
- Persistent volume for `mlruns/` if MLflow moves to filesystem backing in-cluster.

## Related

- Dockerfile that produces the image: [../Dockerfile](../Dockerfile).
- Docker Compose alternative for non-K8s envs: [../docker-compose.yml](../docker-compose.yml).
- Secrets resolution: [security/secrets.py](../../security/secrets.py).
