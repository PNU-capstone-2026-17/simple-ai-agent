# Minikube 배포 가이드 (간단)

1) Minikube의 Docker 환경을 사용해 이미지를 빌드 (Linux/macOS):

```bash
eval $(minikube -p minikube docker-env)
docker build -t simple-ai-agent:local .
```

Windows PowerShell (minikube가 설치되어 있을 때): Docker Desktop이 먼저 실행 중이어야 합니다.

```powershell
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
docker build -t simple-ai-agent:local .
```

또는 한 번에 실행하려면 아래 스크립트를 사용합니다:

```powershell
.\scripts\deploy_minikube.ps1
```

이 스크립트는 `minikube start`부터 이미지 빌드, Secret 생성, 매니페스트 적용까지 순서대로 처리합니다.

`minikube -p minikube docker-env --shell powershell | Invoke-Expression`를 단독으로 복붙하면, Minikube가 아직 시작되지 않은 상태에서 실패할 수 있습니다.

2) 네임스페이스를 만들고, 민감한 값은 `.env` 파일로 Secret을 생성한 뒤 배포합니다:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic simple-ai-agent-secret \
	--from-env-file=.env \
	-n simple-ai-agent
```

`.env` 안의 키들은 `KEY=value` 형식이어야 하며, 실제 파일은 Git에 올리지 않는 것이 좋습니다.

3) ConfigMap과 나머지 리소스를 적용합니다:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

4) 접근 방법 예시:

- `minikube service simple-ai-agent -n simple-ai-agent --url` 로 외부 접근 URL 확인
- 또는 `kubectl port-forward svc/simple-ai-agent 8000:8000 -n simple-ai-agent` 후 localhost:8000 접속

5) 로그 확인 및 디버깅:

```bash
kubectl get pods -n simple-ai-agent
kubectl logs -l app=simple-ai-agent -n simple-ai-agent -f
```

참고: 이 매니페스트는 데모용 최소 설정입니다. 프로덕션에서는 리소스 제한, 프로브 튜닝, 이미지 레지스트리, 비밀 관리 등을 추가하세요.
