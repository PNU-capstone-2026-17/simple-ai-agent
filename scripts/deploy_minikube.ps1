[CmdletBinding()]
param(
    [string]$Namespace = 'simple-ai-agent',
    [string]$ImageName = 'simple-ai-agent:local',
    [string]$EnvFile = '.env'
)

$ErrorActionPreference = 'Stop'

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$StepName
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed with exit code $LASTEXITCODE. Verify that Docker Desktop is running and that minikube can start before retrying."
    }
}

Write-Host 'Starting minikube if needed...'
Invoke-NativeCommand -Command { minikube start } -StepName 'minikube start'

Write-Host 'Pointing Docker to the minikube engine...'
Invoke-NativeCommand -Command { & minikube -p minikube docker-env --shell powershell | Invoke-Expression } -StepName 'minikube docker-env'

Write-Host "Building image: $ImageName"
Invoke-NativeCommand -Command { docker build -t $ImageName . } -StepName 'docker build'

Write-Host "Applying namespace: $Namespace"
Invoke-NativeCommand -Command { kubectl apply -f k8s/namespace.yaml } -StepName 'kubectl apply namespace'

Write-Host "Refreshing Secret: simple-ai-agent-secret"
Invoke-NativeCommand -Command { kubectl delete secret simple-ai-agent-secret -n $Namespace --ignore-not-found=true } -StepName 'kubectl delete secret'

if (Test-Path $EnvFile) {
    Invoke-NativeCommand -Command { kubectl create secret generic simple-ai-agent-secret --from-env-file=$EnvFile -n $Namespace } -StepName 'kubectl create secret'
} else {
    Write-Warning "Env file '$EnvFile' not found. Skipping Secret creation."
}

Write-Host 'Applying ConfigMap, Deployment, and Service...'
Invoke-NativeCommand -Command { kubectl apply -f k8s/configmap.yaml } -StepName 'kubectl apply configmap'
Invoke-NativeCommand -Command { kubectl apply -f k8s/deployment.yaml } -StepName 'kubectl apply deployment'
Invoke-NativeCommand -Command { kubectl apply -f k8s/service.yaml } -StepName 'kubectl apply service'

Write-Host ''
Write-Host 'Done.'
Write-Host "Use: kubectl get pods -n $Namespace"
Write-Host "Use: minikube service simple-ai-agent -n $Namespace --url"
