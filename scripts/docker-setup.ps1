<#
.SYNOPSIS
    MPMB Copilot - Docker Setup Automation Script

.DESCRIPTION
    Automates the Docker environment setup process:
    - Checks Docker installation and status
    - Stops existing containers
    - Builds fresh Docker images
    - Starts all services
    - Waits for health checks
    - Displays service status

.PARAMETER Clean
    Clean volumes (WARNING: Deletes all data including Qdrant vectors and PostgreSQL database)

.PARAMETER SkipBuild
    Skip Docker image rebuild (use existing images)

.EXAMPLE
    .\scripts\docker-setup.ps1
    Standard setup - stops, rebuilds, and starts containers

.EXAMPLE
    .\scripts\docker-setup.ps1 -Clean
    Full clean setup - removes volumes and rebuilds everything

.EXAMPLE
    .\scripts\docker-setup.ps1 -SkipBuild
    Quick restart without rebuilding images
#>

param(
    [switch]$Clean,
    [switch]$SkipBuild
)

# Color functions for better output
function Write-Success { param($Message) Write-Host "[✓] $Message" -ForegroundColor Green }
function Write-Info { param($Message) Write-Host "[i] $Message" -ForegroundColor Cyan }
function Write-Warning { param($Message) Write-Host "[!] $Message" -ForegroundColor Yellow }
function Write-Failure { param($Message) Write-Host "[✗] $Message" -ForegroundColor Red }
function Write-Step { param($Message) Write-Host "`n=== $Message ===" -ForegroundColor Magenta }

# Configuration
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$MaxHealthCheckAttempts = 30
$HealthCheckInterval = 2  # seconds

# Change to project root
Set-Location $ProjectRoot

Write-Host @"

╔════════════════════════════════════════════════════════════════╗
║         MPMB Copilot - Docker Environment Setup                ║
╚════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# Step 1: Check Docker Installation
Write-Step "Step 1: Checking Docker Installation"

try {
    $dockerVersion = docker --version 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Success "Docker installed: $dockerVersion"
} catch {
    Write-Failure "Docker is not installed or not in PATH"
    Write-Info "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
}

# Check if Docker is running
try {
    docker ps >$null 2>&1
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Success "Docker daemon is running"
} catch {
    Write-Failure "Docker daemon is not running"
    Write-Info "Please start Docker Desktop and try again"
    exit 1
}

# Check docker-compose
try {
    $composeVersion = docker-compose --version 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Success "Docker Compose available: $composeVersion"
} catch {
    Write-Failure "Docker Compose is not available"
    exit 1
}

# Step 2: Stop Existing Containers
Write-Step "Step 2: Stopping Existing Containers"

try {
    docker-compose down 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Stopped and removed existing containers"
    } else {
        Write-Warning "No existing containers to stop (this is fine)"
    }
} catch {
    Write-Warning "Error stopping containers (continuing anyway)"
}

# Step 2.5: Clean Volumes (if requested)
if ($Clean) {
    Write-Step "Step 2.5: Cleaning Docker Volumes (DESTRUCTIVE)"

    Write-Warning "This will DELETE all data including:"
    Write-Warning "  - Qdrant vector database"
    Write-Warning "  - PostgreSQL database"
    Write-Warning "  - Application logs"

    $confirmation = Read-Host "`nAre you sure? Type 'YES' to confirm"

    if ($confirmation -eq 'YES') {
        try {
            docker-compose down -v 2>&1 | Out-Null
            Write-Success "Volumes removed successfully"
        } catch {
            Write-Failure "Error removing volumes"
            exit 1
        }
    } else {
        Write-Info "Volume cleanup cancelled - keeping existing data"
    }
}

# Step 3: Build Docker Images
if (-not $SkipBuild) {
    Write-Step "Step 3: Building Docker Images"
    Write-Info "This may take several minutes on first run..."

    try {
        # ! Commented out for faster rebuilds during development
        docker-compose build # --no-cache
        if ($LASTEXITCODE -ne 0) { throw }
        Write-Success "Docker images built successfully"
    } catch {
        Write-Failure "Failed to build Docker images"
        Write-Info "Check the output above for errors"
        exit 1
    }
} else {
    Write-Step "Step 3: Skipping Docker Build (using existing images)"
}

# Step 4: Start Containers
Write-Step "Step 4: Starting Docker Containers"

try {
    docker-compose up -d
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Success "Containers started in detached mode"
} catch {
    Write-Failure "Failed to start containers"
    Write-Info "Run 'docker-compose logs' to see error details"
    exit 1
}

# Step 5: Wait for Health Checks
Write-Step "Step 5: Waiting for Services to be Ready"

$services = @(
    @{Name="PostgreSQL"; Container="mpmb-postgres"; Port=5432},
    @{Name="Qdrant"; Container="mpmb-qdrant"; Port=6333},
    @{Name="Backend"; Container="mpmb-backend"; Port=8000}
)

function Test-ServiceHealth {
    param($Container)

    $health = docker inspect --format='{{.State.Health.Status}}' $Container 2>$null
    if ($health -eq "healthy") { return $true }

    $running = docker inspect --format='{{.State.Running}}' $Container 2>$null
    if ($running -eq "true") { return $true }

    return $false
}

$allHealthy = $false
$attempt = 0

while (-not $allHealthy -and $attempt -lt $MaxHealthCheckAttempts) {
    $attempt++
    Write-Host "`rAttempt $attempt/$MaxHealthCheckAttempts - Checking health..." -NoNewline

    $healthyCount = 0
    foreach ($service in $services) {
        if (Test-ServiceHealth -Container $service.Container) {
            $healthyCount++
        }
    }

    if ($healthyCount -eq $services.Count) {
        $allHealthy = $true
        Write-Host ""  # New line
        Write-Success "All services are healthy!"
    } else {
        Start-Sleep -Seconds $HealthCheckInterval
    }
}

if (-not $allHealthy) {
    Write-Host ""  # New line
    Write-Warning "Services did not become healthy within timeout"
    Write-Info "Checking container status..."
    docker-compose ps
    Write-Info "`nRun 'docker-compose logs' to see detailed logs"
}

# Step 6: Verify Service Connectivity
Write-Step "Step 6: Verifying Service Connectivity"

# Test PostgreSQL
try {
    $pgTest = docker exec mpmb-postgres pg_isready -U mpmb_user -d mpmb_copilot 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "PostgreSQL: Ready and accepting connections"
    } else {
        Write-Warning "PostgreSQL: May not be fully initialized yet"
    }
} catch {
    Write-Warning "PostgreSQL: Unable to verify connection"
}

# Test Qdrant
try {
    $qdrantTest = Invoke-WebRequest -Uri "http://localhost:6333/healthz" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($qdrantTest.StatusCode -eq 200) {
        Write-Success "Qdrant: Healthy and responding"
    }
} catch {
    Write-Warning "Qdrant: Not responding yet (may still be starting)"
}

# Test Backend
try {
    $backendTest = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 5 -UseBasicParsing 2>$null
    if ($backendTest.StatusCode -eq 200) {
        Write-Success "Backend: Healthy and responding"
    }
} catch {
    Write-Warning "Backend: Not responding yet (may still be starting)"
}

# Step 7: Display Service Status
Write-Step "Step 7: Service Status Summary"

Write-Host "`nDocker Containers:" -ForegroundColor Cyan
docker-compose ps

Write-Host "`n" -NoNewline
Write-Host "Service URLs:" -ForegroundColor Cyan
Write-Info "Backend API:       http://localhost:8000"
Write-Info "API Docs:          http://localhost:8000/api/docs"
Write-Info "Health Check:      http://localhost:8000/api/health"
Write-Info "Qdrant Dashboard:  http://localhost:6333/dashboard"
Write-Info "PostgreSQL:        localhost:5432 (user: mpmb_user, db: mpmb_copilot)"

# Step 8: Quick Smoke Test
Write-Step "Step 8: Running Quick Smoke Test"

Start-Sleep -Seconds 2  # Give backend a moment to fully start

try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 10

    Write-Info "Environment: $($healthResponse.environment)"
    Write-Info "Version: $($healthResponse.version)"
    Write-Info "Overall Status: $($healthResponse.status)"

    Write-Host "`nService Health:" -ForegroundColor Cyan
    foreach ($service in $healthResponse.services.PSObject.Properties) {
        $status = $service.Value.status
        $message = $service.Value.message

        $color = switch ($status) {
            "healthy" { "Green" }
            "configured" { "Green" }
            "ready" { "Green" }
            "degraded" { "Yellow" }
            "unavailable" { "Red" }
            "not_configured" { "Yellow" }
            default { "White" }
        }

        Write-Host "  $($service.Name): " -NoNewline
        Write-Host "$status" -ForegroundColor $color -NoNewline
        if ($message) {
            Write-Host " - $message" -ForegroundColor Gray
        } else {
            Write-Host ""
        }
    }

    Write-Host ""
    Write-Success "Smoke test passed - API is responding!"

} catch {
    Write-Warning "Backend API is not fully ready yet"
    Write-Info "Give it a few more seconds and try: curl http://localhost:8000/api/health"
}

# Final Summary
Write-Host @"

╔════════════════════════════════════════════════════════════════╗
║                    Setup Complete!                             ║
╚════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

Write-Host "Your MPMB Copilot development environment is ready!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open API docs: " -NoNewline; Write-Host "http://localhost:8000/api/docs" -ForegroundColor Cyan
Write-Host "  2. Check logs: " -NoNewline; Write-Host "docker-compose logs -f backend" -ForegroundColor Cyan
Write-Host "  3. Run tests: " -NoNewline; Write-Host "cd backend && uv run pytest" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop services: " -NoNewline; Write-Host "docker-compose down" -ForegroundColor Cyan
Write-Host "To view logs: " -NoNewline; Write-Host "docker-compose logs -f [service]" -ForegroundColor Cyan
Write-Host "To restart: " -NoNewline; Write-Host ".\scripts\docker-setup.ps1" -ForegroundColor Cyan
Write-Host ""
