<#
.SYNOPSIS
    Prepare the local environment and rebuild the chunked MPMB corpus.

.DESCRIPTION
    This script is intentionally small in scope. It only:
    1. Creates `.env` from `.env.example` when it is missing
    2. Resolves source paths from environment variables or `.env`
    3. Installs the backend Python dependencies with `uv` (skip with -SkipDependencies)
    4. Reports the ONNX execution provider and, on a first run, opts into GPU inference
    5. Clones or updates the required repositories
    6. Runs the source analyzer, then `scripts/chunk_mpmb.py` inside the backend environment

    It does not build Docker, start services, or trigger indexing.

    Supported `.env` / environment variable overrides:
      DATA_DIR
      MPMB_SOURCE_DIR
      MPMB_SOURCE_2024_DIR
      MPMB_REPO_URL
      MPMB_REPO_2024_URL
      MPMB_REPO_BRANCH_2014
      MPMB_REPO_BRANCH_2024
      IMPORTS_SOURCE_DIR
      IMPORTS_REPO_URL
      CHUNKED_OUTPUT_DIR
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
	# Reuse the existing backend/.venv instead of running `uv sync` first
	[switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"
$ChunkScript = Join-Path $ProjectRoot "scripts\chunk_mpmb.py"
$BackendDir = Join-Path $ProjectRoot "backend"
$UvCacheDir = ".uv-cache"

function Write-Log {
	param(
		[string]$Message,
		[ValidateSet("INFO", "SUCCESS", "WARNING", "ERROR")][string]$Level = "INFO"
	)

	$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
	$line = "[{0}] [{1}] {2}" -f $timestamp, $Level, $Message

	switch ($Level) {
		"SUCCESS" { Write-Host $line -ForegroundColor Green }
		"WARNING" { Write-Host $line -ForegroundColor Yellow }
		"ERROR" { Write-Host $line -ForegroundColor Red }
		default { Write-Host $line }
	}
}

function Test-CommandExists {
	param([string]$Command)
	return $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Get-DotEnvValues {
	param([string]$Path)

	$values = @{}
	if (-not (Test-Path -LiteralPath $Path)) {
		return $values
	}

	foreach ($line in Get-Content -LiteralPath $Path) {
		$trimmed = $line.Trim()
		if (-not $trimmed -or $trimmed.StartsWith("#")) {
			continue
		}

		$separatorIndex = $trimmed.IndexOf("=")
		if ($separatorIndex -lt 1) {
			continue
		}

		$key = $trimmed.Substring(0, $separatorIndex).Trim()
		$value = $trimmed.Substring($separatorIndex + 1).Trim()

		if (
			($value.StartsWith('"') -and $value.EndsWith('"')) -or
			($value.StartsWith("'") -and $value.EndsWith("'"))
		) {
			$value = $value.Substring(1, $value.Length - 2)
		}

		$values[$key] = $value
	}

	return $values
}

function Get-SettingValue {
	param(
		[string]$Name,
		[string]$Default,
		[hashtable]$DotEnvValues
	)

	$envValue = [System.Environment]::GetEnvironmentVariable($Name)
	if (-not [string]::IsNullOrWhiteSpace($envValue)) {
		return $envValue
	}

	if ($DotEnvValues.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace($DotEnvValues[$Name])) {
		return $DotEnvValues[$Name]
	}

	return $Default
}

function Resolve-ProjectPath {
	param([string]$PathValue)

	if ([string]::IsNullOrWhiteSpace($PathValue)) {
		return $null
	}

	if ([System.IO.Path]::IsPathRooted($PathValue)) {
		return [System.IO.Path]::GetFullPath($PathValue)
	}

	return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $PathValue))
}

function Normalize-GitUrl {
	param([string]$Url)

	if ([string]::IsNullOrWhiteSpace($Url)) {
		return ""
	}

	$normalized = $Url.Trim().TrimEnd("/")
	if ($normalized.EndsWith(".git")) {
		$normalized = $normalized.Substring(0, $normalized.Length - 4)
	}

	return $normalized.ToLowerInvariant()
}

function Invoke-ExternalCommand {
	param(
		[string]$FilePath,
		[string[]]$Arguments,
		[string]$WorkingDirectory = $ProjectRoot
	)

	Push-Location $WorkingDirectory
	try {
		$previousErrorActionPreference = $ErrorActionPreference
		$ErrorActionPreference = "Continue"

		$useNativeErrorPreference = $PSVersionTable.PSVersion.Major -ge 7
		if ($useNativeErrorPreference) {
			$previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
			$PSNativeCommandUseErrorActionPreference = $false
		}

		& $FilePath @Arguments
		if ($LASTEXITCODE -ne 0) {
			$argumentText = if ($Arguments) { $Arguments -join " " } else { "" }
			throw "Command failed: $FilePath $argumentText"
		}
	}
	catch {
		throw
	}
 finally {
		$ErrorActionPreference = $previousErrorActionPreference
		if ($useNativeErrorPreference) {
			$PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
		}
		Pop-Location
	}
}

function Get-GitOutput {
	param(
		[string]$RepositoryPath,
		[string[]]$Arguments
	)

	$previousErrorActionPreference = $ErrorActionPreference
	$ErrorActionPreference = "Continue"
	$output = & git -C $RepositoryPath @Arguments 2>&1
	$exitCode = $LASTEXITCODE
	$ErrorActionPreference = $previousErrorActionPreference

	if ($exitCode -ne 0) {
		return $null
	}

	$cleanOutput = @(
		$output |
		ForEach-Object { $_.ToString().TrimEnd() } |
		Where-Object { $_ -and $_ -notmatch '^warning:' }
	)

	return ($cleanOutput | Out-String).Trim()
}

function Get-GitStatusLines {
	param([string]$RepositoryPath)

	$previousErrorActionPreference = $ErrorActionPreference
	$ErrorActionPreference = "Continue"
	$output = & git -C $RepositoryPath status --short 2>&1
	$exitCode = $LASTEXITCODE
	$ErrorActionPreference = $previousErrorActionPreference

	if ($exitCode -ne 0 -or $null -eq $output) {
		return @()
	}

	return @(
		$output |
		ForEach-Object { $_.ToString().TrimEnd() } |
		Where-Object { $_ -and $_ -notmatch '^warning:' }
	)
}

function Ensure-Directory {
	param([string]$Path)

	if (-not (Test-Path -LiteralPath $Path)) {
		if ($script:PSCmdlet.ShouldProcess($Path, "Create directory")) {
			New-Item -ItemType Directory -Path $Path -Force | Out-Null
		}
	}
}

function Normalize-PathValue {
	param([string]$PathValue)

	if ([string]::IsNullOrWhiteSpace($PathValue)) {
		return ""
	}

	return [System.IO.Path]::GetFullPath($PathValue).TrimEnd("\", "/").Replace("\", "/").ToLowerInvariant()
}

function Enable-GitSafeDirectory {
	param([string]$RepositoryPath)

	$resolvedPath = [System.IO.Path]::GetFullPath($RepositoryPath)
	$normalizedResolvedPath = Normalize-PathValue -PathValue $resolvedPath

	$previousErrorActionPreference = $ErrorActionPreference
	$ErrorActionPreference = "Continue"
	$configuredPaths = & git config --global --get-all safe.directory 2>&1
	$exitCode = $LASTEXITCODE
	$ErrorActionPreference = $previousErrorActionPreference

	if ($exitCode -eq 0 -and $null -ne $configuredPaths) {
		$matchesExisting = @(
			$configuredPaths |
			ForEach-Object { $_.ToString().Trim() } |
			Where-Object { (Normalize-PathValue -PathValue $_) -eq $normalizedResolvedPath }
		)
		if ($matchesExisting.Count -gt 0) {
			return
		}
	}

	Write-Log "Adding Git safe.directory for $resolvedPath" -Level INFO
	if ($script:PSCmdlet.ShouldProcess($resolvedPath, "Add Git safe.directory entry")) {
		Invoke-ExternalCommand -FilePath "git" -Arguments @("config", "--global", "--add", "safe.directory", $resolvedPath)
	}
}

function Install-PythonDependencies {
	$lockFile = Join-Path $BackendDir "uv.lock"
	$syncArgs = @("--cache-dir", $UvCacheDir, "sync", "--project", $BackendDir)

	if (-not (Test-Path -LiteralPath $lockFile)) {
		Write-Log "No backend/uv.lock found; resolving dependencies and writing one." -Level WARNING
		if ($script:PSCmdlet.ShouldProcess($BackendDir, "Lock and install backend dependencies")) {
			Invoke-ExternalCommand -FilePath "uv" -Arguments $syncArgs
		}
		return
	}

	# `--locked` installs exactly what uv.lock pins and fails if pyproject.toml has drifted from it, so a routine setup run can never silently re-resolve to different versions
	if ($script:PSCmdlet.ShouldProcess($BackendDir, "Install backend dependencies from uv.lock")) {
		try {
			Invoke-ExternalCommand -FilePath "uv" -Arguments ($syncArgs + @("--locked"))
			return
		}
		catch {
			Write-Log "backend/uv.lock does not match backend/pyproject.toml; re-locking." -Level WARNING
		}

		Invoke-ExternalCommand -FilePath "uv" -Arguments $syncArgs
		Write-Log "backend/uv.lock was updated - commit it so everyone installs the same versions." -Level WARNING
	}
}

function Initialize-EnvFile {
	if (Test-Path -LiteralPath $EnvFile) {
		return
	}

	$examplePath = Join-Path $ProjectRoot ".env.example"
	if (-not (Test-Path -LiteralPath $examplePath)) {
		Write-Log "No .env and no .env.example to seed it from; docker compose needs a .env." -Level WARNING
		return
	}

	Write-Log "No .env found; creating one from .env.example." -Level INFO
	if (-not $script:PSCmdlet.ShouldProcess($EnvFile, "Create .env from .env.example")) {
		return
	}

	# * Point the service addresses at the host: compose sets its own POSTGRES_HOST/QDRANT_HOST for the container, so one .env serves both the containerized backend and a backend run from backend/.venv
	$lines = Get-Content -LiteralPath $examplePath |
	ForEach-Object {
		$_ -replace '^(POSTGRES_HOST=)postgres(?=\s|$)', '${1}127.0.0.1' `
			-replace '^(POSTGRES_PORT=)5432(?=\s|$)', '${1}5433' `
			-replace '^(QDRANT_HOST=)qdrant(?=\s|$)', '${1}127.0.0.1'
	}

	Set-Content -LiteralPath $EnvFile -Value $lines -Encoding utf8
	Write-Log "Created $EnvFile - add your ANTHROPIC_API_KEY before starting the app." -Level WARNING
}

function Get-GpuProviderLabel {
	<#
		Human label of the GPU execution provider onnxruntime exposes in the backend venv,
		or $null when only CPU is available. Asks app.core.onnx_device so the provider
		preference order lives in exactly one place
	#>
	$probe = "from app.core.onnx_device import detect_gpu_provider; d = detect_gpu_provider(); print(d[1] if d else '')"

	$previousErrorActionPreference = $ErrorActionPreference
	$ErrorActionPreference = "Continue"
	$output = & uv --cache-dir $UvCacheDir run --no-sync --project $BackendDir python -c $probe 2>&1
	$exitCode = $LASTEXITCODE
	$ErrorActionPreference = $previousErrorActionPreference

	if ($exitCode -ne 0 -or $null -eq $output) {
		return $null
	}

	$label = @($output | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ }) | Select-Object -Last 1
	if ([string]::IsNullOrWhiteSpace($label)) {
		return $null
	}

	return $label
}

function Initialize-InferenceDevice {
	param([string]$SettingsPath)

	$label = Get-GpuProviderLabel
	if (-not $label) {
		Write-Log "No GPU execution provider found; embedding and reranking will run on CPU." -Level WARNING
		Write-Host "  To add one: pnpm run gpu:install" -ForegroundColor DarkGray
		return
	}

	Write-Log "GPU execution provider available: $label" -Level SUCCESS

	$settings = $null
	if (Test-Path -LiteralPath $SettingsPath) {
		try {
			$settings = Get-Content -Raw -LiteralPath $SettingsPath | ConvertFrom-Json
		}
		catch {
			Write-Log "Could not parse $SettingsPath; leaving it untouched." -Level WARNING
			return
		}
	}

	# ! Never overwrite a deliberate choice: only an absent key gets the detected default
	$current = if ($settings) { $settings.PSObject.Properties["inference_device"] } else { $null }
	if ($current) {
		if ($current.Value -eq "gpu") {
			Write-Log "inference_device is already 'gpu'." -Level INFO
		}
		else {
			Write-Log "inference_device is '$($current.Value)'; leaving it as is. Switch it in Settings -> Compute device to use $label." -Level WARNING
		}
		return
	}

	if (-not $settings) {
		$settings = [pscustomobject]@{}
	}
	$settings | Add-Member -NotePropertyName "inference_device" -NotePropertyValue "gpu"

	if ($script:PSCmdlet.ShouldProcess($SettingsPath, "Set inference_device to gpu")) {
		($settings | ConvertTo-Json -Depth 10) + "`n" | Set-Content -LiteralPath $SettingsPath -Encoding utf8 -NoNewline
		Write-Log "Set inference_device to 'gpu' in $SettingsPath" -Level SUCCESS
	}
}

function Sync-GitRepository {
	param(
		[string]$Name,
		[string]$RepositoryUrl,
		[string]$TargetDirectory,
		[string]$Branch,
		[switch]$AllowRemoteRetarget
	)

	$shouldClone = $false

	if (Test-Path -LiteralPath $TargetDirectory) {
		$gitDir = Join-Path $TargetDirectory ".git"
		if (-not (Test-Path -LiteralPath $gitDir)) {
			$existingItems = @(Get-ChildItem -LiteralPath $TargetDirectory -Force)
			$allowedPlaceholderNames = @(".gitkeep", ".gitignore", "README.md")
			$nonPlaceholderItems = @(
				$existingItems |
				Where-Object { $allowedPlaceholderNames -notcontains $_.Name }
			)

			if ($nonPlaceholderItems.Count -gt 0) {
				$itemList = $nonPlaceholderItems | ForEach-Object { $_.Name } | Sort-Object
				throw "$Name target exists but is not a git repository and contains non-placeholder files: $TargetDirectory (`"$($itemList -join '", "')`")"
			}

			if ($existingItems.Count -gt 0) {
				Write-Log "$Name target only contains placeholder files; preparing it for clone." -Level INFO
				foreach ($item in $existingItems) {
					if ($script:PSCmdlet.ShouldProcess($item.FullName, "Remove placeholder before cloning $Name")) {
						Remove-Item -LiteralPath $item.FullName -Force -Recurse
					}
				}
			}

			$shouldClone = $true
		}
	}

	if ((-not $shouldClone) -and (Test-Path -LiteralPath (Join-Path $TargetDirectory ".git"))) {
		Enable-GitSafeDirectory -RepositoryPath $TargetDirectory

		$skipExistingRepoUpdate = $false
		$originUrl = Get-GitOutput -RepositoryPath $TargetDirectory -Arguments @("remote", "get-url", "origin")
		if (-not $originUrl) {
			if ($WhatIfPreference) {
				Write-Log "Unable to read origin URL for $Name during -WhatIf; skipping remote validation." -Level WARNING
				$skipExistingRepoUpdate = $true
			}
			else {
				throw "Unable to read origin URL for $Name at $TargetDirectory"
			}
		}

		if ((-not $skipExistingRepoUpdate) -and ((Normalize-GitUrl $originUrl) -ne (Normalize-GitUrl $RepositoryUrl))) {
			if ($AllowRemoteRetarget) {
				Write-Log "$Name target points at $originUrl; retargeting origin to $RepositoryUrl." -Level INFO
				if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Retarget origin for $Name")) {
					Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "remote", "set-url", "origin", $RepositoryUrl)
					Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
				}
			}
			else {
				throw "$Name target points at a different repository: $originUrl"
			}
		}

		if ((-not $skipExistingRepoUpdate) -and $AllowRemoteRetarget) {
			if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Normalize fetch refspec for $Name")) {
				Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
			}
		}

		$currentBranch = Get-GitOutput -RepositoryPath $TargetDirectory -Arguments @("rev-parse", "--abbrev-ref", "HEAD")
		$statusLines = if ($skipExistingRepoUpdate) { @() } else { Get-GitStatusLines -RepositoryPath $TargetDirectory }

		if ($skipExistingRepoUpdate) {
			Write-Log "Continuing with the existing checkout for $Name." -Level INFO
		}
		elseif ($statusLines.Count -gt 0) {
			Write-Log "$Name has local changes; skipping update to avoid overwriting them." -Level WARNING
			if ($currentBranch) {
				Write-Host "  Branch:  $currentBranch" -ForegroundColor DarkYellow
			}
			if ($statusLines.Count -le 5) {
				Write-Host "  Changes:" -ForegroundColor DarkYellow
				foreach ($line in $statusLines) {
					Write-Host "    $line" -ForegroundColor DarkYellow
				}
			}
			else {
				Write-Host "  Changes: $($statusLines.Count) entries" -ForegroundColor DarkYellow
			}
			Write-Log "Continuing with the existing checkout for $Name." -Level INFO
		}
		else {
			Write-Log "Updating $Name..." -Level INFO
			try {
				if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Fetch latest changes for $Name")) {
					Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "fetch", "--all", "--prune")
				}

				if ($Branch) {
					if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Checkout branch $Branch for $Name")) {
						Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "checkout", $Branch)
					}

					if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Pull branch $Branch for $Name")) {
						Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "pull", "--ff-only", "origin", $Branch)
					}
				}
				else {
					if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Pull latest changes for $Name")) {
						Invoke-ExternalCommand -FilePath "git" -Arguments @("-C", $TargetDirectory, "pull", "--ff-only")
					}
				}
			}
			catch {
				Write-Log "Unable to update $Name cleanly; continuing with the existing checkout." -Level WARNING
				Write-Log $_.Exception.Message -Level WARNING
			}
		}
	}
	elseif ($shouldClone -or (-not (Test-Path -LiteralPath $TargetDirectory))) {
		$parent = Split-Path -Parent $TargetDirectory
		Ensure-Directory -Path $parent

		$cloneArgs = @("clone")
		if ($Branch) {
			$cloneArgs += @("--branch", $Branch, "--single-branch")
		}
		$cloneArgs += @($RepositoryUrl, $TargetDirectory)

		Write-Log "Cloning $Name..." -Level INFO
		if ($script:PSCmdlet.ShouldProcess($TargetDirectory, "Clone $Name")) {
			Invoke-ExternalCommand -FilePath "git" -Arguments $cloneArgs
		}
	}

	if (Test-Path -LiteralPath (Join-Path $TargetDirectory ".git")) {
		Enable-GitSafeDirectory -RepositoryPath $TargetDirectory

		$currentBranch = Get-GitOutput -RepositoryPath $TargetDirectory -Arguments @("rev-parse", "--abbrev-ref", "HEAD")
		$currentCommit = Get-GitOutput -RepositoryPath $TargetDirectory -Arguments @("rev-parse", "--short", "HEAD")

		if ($currentBranch -and $currentCommit) {
			Write-Log "$Name ready at $currentBranch ($currentCommit)" -Level SUCCESS
		}
		else {
			Write-Log "$Name ready at $TargetDirectory" -Level SUCCESS
		}
	}
}

Set-Location $ProjectRoot

Write-Host ""
Write-Host "MPMB source setup" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot" -ForegroundColor DarkGray
Write-Host ""

if (-not (Test-CommandExists "git")) {
	Write-Log "Git is required but was not found in PATH." -Level ERROR
	exit 1
}

if (-not (Test-CommandExists "uv")) {
	Write-Log "uv is required but was not found in PATH." -Level ERROR
	Write-Host "  Install it, then re-run this script:" -ForegroundColor DarkGray
	Write-Host "    https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor DarkGray
	Write-Host "    winget install --id=astral-sh.uv -e" -ForegroundColor DarkGray
	exit 1
}

# The chunker reads the analyzer report, and the analyzer is a pnpm workspace package
if (-not (Test-CommandExists "pnpm")) {
	Write-Log "pnpm is required but was not found in PATH." -Level ERROR
	Write-Host "  Install it, then re-run this script: https://pnpm.io/installation" -ForegroundColor DarkGray
	exit 1
}

Initialize-EnvFile

$dotEnvValues = Get-DotEnvValues -Path $EnvFile

$dataDir = Resolve-ProjectPath (Get-SettingValue -Name "DATA_DIR" -Default "./data" -DotEnvValues $dotEnvValues)
$mpmbSourceDir = Resolve-ProjectPath (Get-SettingValue -Name "MPMB_SOURCE_DIR" -Default "./data/mpmb_source" -DotEnvValues $dotEnvValues)
$mpmbSource2024Dir = Resolve-ProjectPath (Get-SettingValue -Name "MPMB_SOURCE_2024_DIR" -Default "./data/mpmb_source_2024" -DotEnvValues $dotEnvValues)
$importsSourceDir = Resolve-ProjectPath (Get-SettingValue -Name "IMPORTS_SOURCE_DIR" -Default "./data/imports_source" -DotEnvValues $dotEnvValues)
$chunkedOutputDir = Resolve-ProjectPath (Get-SettingValue -Name "CHUNKED_OUTPUT_DIR" -Default "./data/chunked_output" -DotEnvValues $dotEnvValues)

$mpmbRepoUrl = Get-SettingValue -Name "MPMB_REPO_URL" -Default "https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git" -DotEnvValues $dotEnvValues
$mpmbRepo2024Url = Get-SettingValue -Name "MPMB_REPO_2024_URL" -Default "https://github.com/morepurplemorebetter/2024_MPMBs-Character-Record-Sheet.git" -DotEnvValues $dotEnvValues
$mpmbRepoBranch2014 = Get-SettingValue -Name "MPMB_REPO_BRANCH_2014" -Default "master" -DotEnvValues $dotEnvValues
$mpmbRepoBranch2024 = Get-SettingValue -Name "MPMB_REPO_BRANCH_2024" -Default "main" -DotEnvValues $dotEnvValues
$importsRepoUrl = Get-SettingValue -Name "IMPORTS_REPO_URL" -Default "https://github.com/safety-orange/Imports-for-MPMB-s-Character-Sheet.git" -DotEnvValues $dotEnvValues

Write-Log "Using source paths:" -Level INFO
Write-Host "  2014 repo:  $mpmbSourceDir" -ForegroundColor Gray
Write-Host "  2024 repo:  $mpmbSource2024Dir" -ForegroundColor Gray
Write-Host "  Imports:    $importsSourceDir" -ForegroundColor Gray
Write-Host "  Chunks:     $chunkedOutputDir" -ForegroundColor Gray
Write-Host ""

Ensure-Directory -Path $dataDir
Ensure-Directory -Path $chunkedOutputDir
Ensure-Directory -Path (Join-Path $dataDir "index_cache")
Ensure-Directory -Path (Join-Path $dataDir "uploads")

if ($SkipDependencies) {
	Write-Log "Skipping the backend dependency install (-SkipDependencies)." -Level WARNING
}
else {
	Write-Log "Installing backend Python dependencies with uv..." -Level INFO
	Install-PythonDependencies
	Write-Log "Backend environment ready at $(Join-Path $BackendDir '.venv')" -Level SUCCESS
}

Initialize-InferenceDevice -SettingsPath (Join-Path $dataDir "settings.json")

Sync-GitRepository `
	-Name "MPMB main repo (2014)" `
	-RepositoryUrl $mpmbRepoUrl `
	-TargetDirectory $mpmbSourceDir `
	-Branch $mpmbRepoBranch2014

Sync-GitRepository `
	-Name "MPMB main repo (2024)" `
	-RepositoryUrl $mpmbRepo2024Url `
	-TargetDirectory $mpmbSource2024Dir `
	-Branch $mpmbRepoBranch2024 `
	-AllowRemoteRetarget

Sync-GitRepository `
	-Name "Imports repo" `
	-RepositoryUrl $importsRepoUrl `
	-TargetDirectory $importsSourceDir `
	-Branch ""

Write-Log "Running the source analyzer..." -Level INFO
if ($script:PSCmdlet.ShouldProcess($ProjectRoot, "Run the source analyzer")) {
	# ! The chunker hard-fails without scripts/analyze/reports/mpmb-analysis.json, and the report has to be rebuilt from the source trees that were just updated
	Invoke-ExternalCommand -FilePath "pnpm" -Arguments @("run", "analyze")
}

Write-Log "Starting chunker..." -Level INFO
if ($script:PSCmdlet.ShouldProcess($ChunkScript, "Run the MPMB chunker")) {
	Invoke-ExternalCommand -FilePath "uv" -Arguments @(
		"--cache-dir", $UvCacheDir,
		"run", "--no-sync", "--project", $BackendDir,
		"python", $ChunkScript
	)
}

Write-Log "Setup complete." -Level SUCCESS
