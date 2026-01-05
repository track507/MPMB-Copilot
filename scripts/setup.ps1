<#
.SYNOPSIS
    MPMB Copilot - Complete Development Environment Startup

.DESCRIPTION
    Comprehensive startup script that:
    - Validates prerequisites (Docker, Git, Python, uv)
    - Clones/updates MPMB source repository
    - Runs code chunking pipeline
    - Builds and starts Docker containers
    - Indexes chunks into Qdrant
    - Verifies complete system health

.PARAMETER FullRebuild
    Force complete rebuild (clean volumes, rebuild images, re-chunk, re-index)

.PARAMETER SkipChunking
    Skip the chunking step (use existing chunks)

.PARAMETER SkipIndexing
    Skip the Qdrant indexing step

.PARAMETER SkipDocker
    Skip Docker operations (for testing data pipeline only)

.EXAMPLE
    .\scripts\startup.ps1
    Standard startup - updates source, chunks, and starts services

.EXAMPLE
    .\scripts\startup.ps1 -FullRebuild
    Complete clean rebuild of everything

.EXAMPLE
    .\scripts\startup.ps1 -SkipChunking -SkipIndexing
    Just restart Docker without touching data pipeline
#>

param(
    [switch]$FullRebuild,
    [switch]$SkipChunking,
    [switch]$SkipIndexing,
    [switch]$SkipDocker
)

# ============================================================================
# Configuration
# ============================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $ProjectRoot "data"
$MPMBSourceDir = Join-Path $DataDir "mpmb_source"
$ChunkedOutputDir = Join-Path $DataDir "chunked_output"
$ChunkScript = Join-Path $ProjectRoot "scripts\chunk_mpmb.py"
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"

$MPMBRepoUrl = "https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git"
$MaxHealthCheckAttempts = 30
$HealthCheckInterval = 2

# ============================================================================
# Helper Functions
# ============================================================================

# Unified logging function with colors
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet('INFO','SUCCESS','WARNING','ERROR')][string]$Level = 'INFO'
    )
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $line = "[{0}] [{1}]: {2}" -f $ts, $Level, $Message

    switch ($Level) {
        "ERROR" { Write-Host $line -ForegroundColor Red }
        "SUCCESS" { Write-Host $line -ForegroundColor Green }
        "WARNING" { Write-Host $line -ForegroundColor Yellow }
        default { Write-Host $line }
    }
}

function Write-Step {
    param($Message)
    Write-Host "`n━━━ $Message ━━━" -ForegroundColor Magenta
}

function Write-Section {
    param($Message)
    Write-Host "`n╔$('═' * 70)╗" -ForegroundColor Cyan
    Write-Host "║ $($Message.PadRight(68)) ║" -ForegroundColor Cyan
    Write-Host "╚$('═' * 70)╝" -ForegroundColor Cyan
}

function Test-CommandExists {
    param($Command)
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Invoke-SafeCommand {
    param(
        [string]$Description,
        [scriptblock]$Command,
        [bool]$ContinueOnError = $false
    )

    try {
        Write-Log $Description -Level INFO
        & $Command
        if ($LASTEXITCODE -ne 0 -and -not $ContinueOnError) {
            throw "Command failed with exit code $LASTEXITCODE"
        }
        return $true
    } catch {
        Write-Log "$Description failed: $_" -Level ERROR
        if (-not $ContinueOnError) {
            throw
        }
        return $false
    }
}

# ============================================================================
# Main Script
# ============================================================================

Set-Location $ProjectRoot

Write-Host @"

╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║              MPMB Copilot - Development Environment Startup            ║
║                                                                        ║
║  This script will set up your complete development environment:        ║
║    • Update MPMB source code repository                                ║
║    • Generate code chunks for RAG indexing                             ║
║    • Build and start Docker containers                                 ║
║    • Index chunks into Qdrant vector database                          ║
║    • Verify system health                                              ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

Start-Sleep -Seconds 1

# ============================================================================
# Phase 0: Prerequisites Check
# ============================================================================

Write-Section "Phase 0: Validating Prerequisites"

# Check Git
if (Test-CommandExists "git") {
    $gitVersion = git --version
    Write-Log "Git: $gitVersion" -Level SUCCESS
} else {
    Write-Log "Git is not installed" -Level ERROR
    Write-Log "Install from: https://git-scm.com/download/win" -Level INFO
    exit 1
}

# Check Python
if (Test-CommandExists "python") {
    $pythonVersion = python --version
    Write-Log "Python: $pythonVersion" -Level SUCCESS
} else {
    Write-Log "Python is not installed" -Level ERROR
    Write-Log "Install Python 3.11+ from: https://www.python.org/downloads/" -Level INFO
    exit 1
}

# Check uv
if (Test-CommandExists "uv") {
    $uvVersion = uv --version
    Write-Log "uv: $uvVersion" -Level SUCCESS
} else {
    Write-Log "uv is not installed" -Level ERROR
    Write-Log "Install with: pip install uv" -Level INFO
    exit 1
}

if (-not $SkipDocker) {
    # Check Docker
    if (Test-CommandExists "docker") {
        try {
            docker ps >$null 2>&1
            if ($LASTEXITCODE -eq 0) {
                $dockerVersion = docker --version
                Write-Log "Docker: $dockerVersion (daemon running)" -Level SUCCESS
            } else {
                Write-Log "Docker daemon is not running" -Level ERROR
                Write-Log "Please start Docker Desktop" -Level INFO
                exit 1
            }
        } catch {
            Write-Log "Docker is installed but not accessible" -Level ERROR
            exit 1
        }
    } else {
        Write-Log "Docker is not installed" -Level ERROR
        Write-Log "Install from: https://www.docker.com/products/docker-desktop" -Level INFO
        exit 1
    }

    # Check docker-compose
    if (Test-CommandExists "docker-compose") {
        $composeVersion = docker-compose --version
        Write-Log "Docker Compose: $composeVersion" -Level SUCCESS
    } else {
        Write-Log "Docker Compose is not available" -Level ERROR
        exit 1
    }
}

Write-Log "All prerequisites satisfied!" -Level SUCCESS

# ============================================================================
# Phase 1: MPMB Source Repository
# ============================================================================

Write-Section "Phase 1: MPMB Source Code Repository"

# Ensure data directory exists
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    Write-Log "Created data directory" -Level SUCCESS
}

# Handle MPMB repository
if (Test-Path $MPMBSourceDir) {
    Write-Log "MPMB source directory exists - updating repository..." -Level INFO

    Push-Location $MPMBSourceDir
    try {
        # Check if it's a git repository
        $isGitRepo = Test-Path ".git"

        if ($isGitRepo) {
            # Fix Git safe.directory issue (common on Windows)
            $gitConfigResult = git config --get safe.directory $MPMBSourceDir 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "Adding repository to Git safe.directory list..." -Level INFO
                git config --global --add safe.directory $MPMBSourceDir
                Write-Log "Git safe.directory configured" -Level SUCCESS
            }

            # Fetch latest changes
            Write-Log "Fetching latest changes from remote..." -Level INFO
            git fetch origin 2>&1 | Out-Null

            if ($LASTEXITCODE -eq 0) {
                # Check if we're behind
                $localCommit = git rev-parse HEAD 2>$null
                $remoteCommit = git rev-parse origin/master 2>$null
                if (-not $remoteCommit) {
                    $remoteCommit = git rev-parse origin/main 2>$null
                }

                if ($localCommit -eq $remoteCommit) {
                    Write-Log "Already up to date (commit: $($localCommit.Substring(0,7)))" -Level SUCCESS
                } else {
                    Write-Log "Pulling latest changes..." -Level INFO
                    $branch = git rev-parse --abbrev-ref HEAD
                    git pull origin $branch 2>&1 | Out-Null

                    if ($LASTEXITCODE -eq 0) {
                        Write-Log "Updated to latest version (commit: $($remoteCommit.Substring(0,7)))" -Level SUCCESS
                    } else {
                        Write-Log "Git pull encountered issues - repository may need manual attention" -Level WARNING
                    }
                }

                # Show recent commits (if fetch was successful)
                Write-Host "`nRecent commits:" -ForegroundColor Yellow
                git log --oneline --graph --decorate -5 2>$null

            } else {
                Write-Log "Git fetch failed - continuing with existing repository state" -Level WARNING
            }

        } else {
            Write-Log "Directory exists but is not a git repository" -Level WARNING
            Write-Log "Consider removing it and re-running this script" -Level WARNING
        }

    } catch {
        Write-Log "Failed to update repository: $_" -Level ERROR
        Write-Log "Continuing with existing repository state" -Level INFO
    } finally {
        Pop-Location
    }

} else {
    Write-Log "MPMB source directory not found - cloning repository..." -Level INFO
    Write-Log "Repository: $MPMBRepoUrl" -Level INFO

    try {
        git clone $MPMBRepoUrl $MPMBSourceDir 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Log "Successfully cloned MPMB repository" -Level SUCCESS

            # Add to safe.directory immediately after cloning
            git config --global --add safe.directory $MPMBSourceDir 2>$null

            # Show repository info
            Push-Location $MPMBSourceDir
            $commit = git rev-parse --short HEAD 2>$null
            $commitDate = git log -1 --format=%cd --date=short 2>$null
            Write-Log "Cloned commit: $commit (dated: $commitDate)" -Level INFO
            Pop-Location
        } else {
            throw "Git clone failed"
        }

    } catch {
        Write-Log "Failed to clone repository: $_" -Level ERROR
        Write-Log "Check your internet connection and try again" -Level INFO
        exit 1
    }
}

# Count files for verification
$jsFiles = Get-ChildItem -Path $MPMBSourceDir -Filter "*.js" -Recurse -File -ErrorAction SilentlyContinue
if ($jsFiles) {
    Write-Log "Repository contains $($jsFiles.Count) JavaScript files" -Level SUCCESS
} else {
    Write-Log "Warning: No JavaScript files found in repository" -Level WARNING
}

# Count files for verification
$jsFiles = Get-ChildItem -Path $MPMBSourceDir -Filter "*.js" -Recurse -File
Write-Log "Repository contains $($jsFiles.Count) JavaScript files" -Level SUCCESS

# ============================================================================
# Phase 2: Code Chunking
# ============================================================================

if (-not $SkipChunking) {
    Write-Section "Phase 2: Code Chunking Pipeline"

    # Check if chunks already exist
    $existingChunks = $false
    if (Test-Path $ChunkedOutputDir) {
        $chunkFiles = Get-ChildItem -Path $ChunkedOutputDir -Filter "*.json"
        if ($chunkFiles.Count -gt 0) {
            $existingChunks = $true
            Write-Log "Found $($chunkFiles.Count) existing chunk files" -Level INFO

            if (-not $FullRebuild) {
                $response = Read-Host "Re-chunk source code? (y/N)"
                if ($response -ne 'y' -and $response -ne 'Y') {
                    Write-Log "Skipping chunking - using existing chunks" -Level INFO
                    $SkipChunking = $true
                }
            }
        }
    }

    if (-not $SkipChunking -or $FullRebuild) {
        # Ensure output directory exists
        if (-not (Test-Path $ChunkedOutputDir)) {
            New-Item -ItemType Directory -Path $ChunkedOutputDir -Force | Out-Null
        }

        Write-Log "Running chunking script: $ChunkScript" -Level INFO
        Write-Log "This may take 1-2 minutes..." -Level INFO

        try {
            # Run chunking script
            python $ChunkScript

            if ($LASTEXITCODE -eq 0) {
                # Count generated chunks
                $chunkFiles = Get-ChildItem -Path $ChunkedOutputDir -Filter "*.json"
                $totalChunks = 0

                foreach ($file in $chunkFiles) {
                    $content = Get-Content $file.FullName -Raw | ConvertFrom-Json
                    $totalChunks += $content.Count
                }

                Write-Log "Chunking complete!" -Level SUCCESS
                Write-Log "Generated $($chunkFiles.Count) chunk files containing $totalChunks total chunks" -Level INFO

                # Display chunk breakdown
                Write-Host "`nChunk breakdown:" -ForegroundColor Yellow
                foreach ($file in $chunkFiles) {
                    $content = Get-Content $file.FullName -Raw | ConvertFrom-Json
                    Write-Host "  $($file.Name): $($content.Count) chunks" -ForegroundColor Gray
                }

            } else {
                throw "Chunking script failed with exit code $LASTEXITCODE"
            }

        } catch {
            Write-Log "Code chunking failed: $_" -Level ERROR
            Write-Log "Check the chunking script output above for details" -Level INFO
            exit 1
        }
    }

} else {
    Write-Section "Phase 2: Code Chunking (Skipped)"
    Write-Log "Using existing chunks from previous run" -Level INFO
}

# ============================================================================
# Phase 3: Docker Environment
# ============================================================================

if (-not $SkipDocker) {
    Write-Section "Phase 3: Docker Environment Setup"

    # Stop existing containers
    Write-Log "Stopping existing containers..." -Level INFO
    docker-compose down 2>&1 | Out-Null

    if ($FullRebuild) {
        Write-Log "Full rebuild requested - removing volumes..." -Level WARNING
        docker-compose down -v 2>&1 | Out-Null
        Write-Log "Volumes removed" -Level SUCCESS
    }

    # Build images
    Write-Log "Building Docker images (this may take several minutes)..." -Level INFO
    $buildArgs = if ($FullRebuild) { @("build", "--no-cache") } else { @("build") }

    docker-compose $buildArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Docker build failed" -Level ERROR
        exit 1
    }
    Write-Log "Docker images built successfully" -Level SUCCESS

    # Start containers
    Write-Log "Starting Docker containers..." -Level INFO
    docker-compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to start containers" -Level ERROR
        exit 1
    }
    Write-Log "Containers started" -Level SUCCESS

    # Wait for health checks
    Write-Log "Waiting for services to be ready..." -Level INFO

    $services = @(
        @{Name="PostgreSQL"; Container="mpmb-postgres"},
        @{Name="Qdrant"; Container="mpmb-qdrant"},
        @{Name="Backend"; Container="mpmb-backend"}
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

        $healthyServices = @()
        foreach ($service in $services) {
            if (Test-ServiceHealth -Container $service.Container) {
                $healthyServices += $service.Name
            }
        }

        Write-Host "`r[$attempt/$MaxHealthCheckAttempts] Healthy: $($healthyServices -join ', ')".PadRight(80) -NoNewline

        if ($healthyServices.Count -eq $services.Count) {
            $allHealthy = $true
        } else {
            Start-Sleep -Seconds $HealthCheckInterval
        }
    }

    Write-Host ""  # New line

    if ($allHealthy) {
        Write-Log "All services are healthy!" -Level SUCCESS
    } else {
        Write-Log "Some services may not be fully ready" -Level WARNING
        docker-compose ps
    }

    # Verify connectivity
    Write-Log "Verifying service connectivity..." -Level INFO
    Start-Sleep -Seconds 10

    try {
        $healthCheck = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 10
        Write-Log "Backend API is responding" -Level SUCCESS
        Write-Log "Status: $($healthCheck.status) | Environment: $($healthCheck.environment)" -Level INFO
    } catch {
        Write-Log "Backend API not ready yet (may need a few more seconds)" -Level WARNING
    }

} else {
    Write-Section "Phase 3: Docker Environment (Skipped)"
}

# ============================================================================
# Phase 4: Vector Database Indexing
# ============================================================================

if (-not $SkipIndexing -and -not $SkipDocker) {
    Write-Section "Phase 4: Qdrant Vector Database Indexing"

    # Check if Qdrant is ready
    $qdrantReady = $false
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $qdrantHealth = Invoke-WebRequest -Uri "http://127.0.0.1:6333/healthz" -TimeoutSec 3 -UseBasicParsing
            if ($qdrantHealth.StatusCode -eq 200) {
                $qdrantReady = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $qdrantReady) {
        Write-Log "Qdrant is not ready - skipping indexing" -Level WARNING
        Write-Log "You can index later with: curl -X POST http://127.0.0.1:8000/api/index" -Level INFO
    } else {
        Write-Log "Qdrant is ready - checking index status..." -Level INFO

        try {
            $indexStatus = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/index/status" -TimeoutSec 10

            if ($indexStatus.total_vectors -eq 0 -or $FullRebuild) {
                Write-Log "Starting indexing process..." -Level INFO
                Write-Log "This will generate embeddings and upload to Qdrant (may take 2-5 minutes)" -Level INFO

                $indexRequest = @{
                    force_reindex = [bool]$FullRebuild
                } | ConvertTo-Json

                $indexResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/index" `
                    -Method Post `
                    -Body $indexRequest `
                    -ContentType "application/json" `
                    -TimeoutSec 300

                Write-Log "Indexing complete!" -Level SUCCESS
                Write-Log "Files processed: $($indexResponse.files_processed)" -Level INFO
                Write-Log "Chunks created: $($indexResponse.chunks_created)" -Level INFO
                Write-Log "Vectors uploaded: $($indexResponse.vectors_uploaded)" -Level INFO

            } else {
                Write-Log "Index already populated with $($indexStatus.total_vectors) vectors" -Level SUCCESS
                Write-Log "Use -FullRebuild to force re-indexing" -Level INFO
            }

        } catch {
            Write-Log "Indexing API not ready or failed: $_" -Level WARNING
            Write-Log "You can index manually later with:" -Level INFO
            Write-Log "  curl: curl -X POST http://127.0.0.1:8000/api/index -H `"Content-Type: application/json`" -d '{\"force_reindex\": false}'" -Level INFO
            Write-Log "  pwsh: Invoke-RestMethod -Uri http://127.0.0.1:8000/api/index -Method Post -Body '{\"force_reindex\": false}' -ContentType 'application/json'" -Level INFO
        }
    }

} else {
    Write-Section "Phase 4: Vector Database Indexing (Skipped)"
}

# ============================================================================
# Phase 5: System Health Verification
# ============================================================================

if (-not $SkipDocker) {
    Write-Section "Phase 5: System Health Verification"

    Start-Sleep -Seconds 2

    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 10

        Write-Host "`nSystem Status:" -ForegroundColor Cyan
        Write-Host "  Overall: " -NoNewline

        switch ($health.status) {
            "healthy" { Write-Host "HEALTHY ✓" -ForegroundColor Green }
            "degraded" { Write-Host "DEGRADED !" -ForegroundColor Yellow }
            "unhealthy" { Write-Host "UNHEALTHY ✗" -ForegroundColor Red }
            default { Write-Host $health.status -ForegroundColor White }
        }

        Write-Host "  Environment: $($health.environment)"
        Write-Host "  Version: $($health.version)"
        Write-Host "  Timestamp: $($health.timestamp)"

        Write-Host "`nService Health:" -ForegroundColor Cyan
        foreach ($service in $health.services.PSObject.Properties) {
            $status = $service.Value.status
            $message = $service.Value.message

            $color = switch ($status) {
                "healthy" { "Green" }
                "configured" { "Green" }
                "ready" { "Green" }
                default { "Yellow" }
            }

            $icon = if ($status -in @("healthy", "configured", "ready")) { "✓" } else { "!" }

            Write-Host "  $($service.Name): " -NoNewline
            Write-Host "$icon $status" -ForegroundColor $color
            if ($message) {
                Write-Host "    → $message" -ForegroundColor Gray
            }
        }

    } catch {
        Write-Log "Unable to get full health status" -Level WARNING
    }
}

# ============================================================================
# Final Summary
# ============================================================================

Write-Host @"

╔════════════════════════════════════════════════════════════════════════╗
║                                                                        ║
║                         STARTUP COMPLETE!                              ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green

Write-Log "Your MPMB Copilot development environment is fully initialized!" -Level SUCCESS
Write-Host ""

Write-Host "📍 Service URLs:" -ForegroundColor Yellow
Write-Host "   Backend API:       " -NoNewline; Write-Host "http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "   API Documentation: " -NoNewline; Write-Host "http://127.0.0.1:8000/api/docs" -ForegroundColor Cyan
Write-Host "   Health Check:      " -NoNewline; Write-Host "http://127.0.0.1:8000/api/health" -ForegroundColor Cyan
Write-Host "   Qdrant Dashboard:  " -NoNewline; Write-Host "http://127.0.0.1:6333/dashboard" -ForegroundColor Cyan
Write-Host ""

Write-Host "🔧 Quick Commands:" -ForegroundColor Yellow
Write-Host "   View logs:         " -NoNewline; Write-Host "docker-compose logs -f backend" -ForegroundColor Cyan
Write-Host "   Run tests:         " -NoNewline; Write-Host "cd backend && uv run pytest -v" -ForegroundColor Cyan
Write-Host "   Stop services:     " -NoNewline; Write-Host "docker-compose down" -ForegroundColor Cyan
Write-Host "   Restart:           " -NoNewline; Write-Host ".\scripts\startup.ps1" -ForegroundColor Cyan
Write-Host ""

Write-Host "📊 System Stats:" -ForegroundColor Yellow
if (Test-Path $MPMBSourceDir) {
    $jsCount = (Get-ChildItem -Path $MPMBSourceDir -Filter "*.js" -Recurse).Count
    Write-Host "   MPMB JS Files:     " -NoNewline; Write-Host "$jsCount files" -ForegroundColor Cyan
}
if (Test-Path $ChunkedOutputDir) {
    $chunkFiles = Get-ChildItem -Path $ChunkedOutputDir -Filter "*.json"
    Write-Host "   Chunk Files:       " -NoNewline; Write-Host "$($chunkFiles.Count) files" -ForegroundColor Cyan
}

try {
    $indexStatus = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/index/status" -TimeoutSec 5 -ErrorAction SilentlyContinue
    Write-Host "   Indexed Vectors:   " -NoNewline; Write-Host "$($indexStatus.total_vectors) vectors" -ForegroundColor Cyan
} catch {}

Write-Host ""
Write-Log "Happy coding! 🎉" -Level SUCCESS
Write-Host ""
