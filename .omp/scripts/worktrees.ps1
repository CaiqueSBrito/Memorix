# Cria um worktree Orca para cada tarefa aberta em .omp/tasks/ (ver "Worktrees" em .omp/pipeline/pipeline.md).
# Uso, do checkout principal:  powershell -File .omp/scripts/worktrees.ps1 [-Base develop] [-Agent omp]
# -Agent: comando aberto num terminal do worktree depois do setup (omp, claude, codex...).
param([string]$Base = "develop", [string]$Agent)
$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel) -replace '\\', '/'
if ((git rev-parse --git-dir) -ne (git rev-parse --git-common-dir)) { throw "Rode no checkout principal, nao num worktree." }

$existing = (git worktree list --porcelain) -match '^branch ' -replace '^branch refs/heads/', ''

foreach ($task in Get-ChildItem "$root/.omp/tasks" -Filter '*.md' | Where-Object Name -match '^\d{3}-') {
    $estado = (Get-Content $task.FullName -TotalCount 5 -Encoding UTF8 | Select-String 'Estado:\s*(\S+)').Matches.Groups[1].Value
    if ($estado -match '^(Conclu|Cancelad)') { continue }
    $name = $task.BaseName
    if ($existing | Where-Object { $_ -match "(^|/)$([regex]::Escape($name))$" }) { Write-Host "= $name (ja existe)"; continue }

    $cmd = @('worktree', 'create', '--repo', "path:$root", '--name', $name, '--base-branch', $Base, '--no-parent', '--setup', 'skip', '--json')
    $out = orca @cmd | Out-String
    if ($LASTEXITCODE) { throw "orca falhou para ${name}: $out" }
    $wt = (git worktree list --porcelain | Select-String '^worktree (.+)$' | ForEach-Object { $_.Matches.Groups[1].Value } |
        Where-Object { $_ -ne $root -and (git -C $_ branch --show-current) -match "(^|/)$([regex]::Escape($name))$" } | Select-Object -First 1)
    if (-not $wt) { throw "Worktree de $name nao encontrado depois do create: $out" }

    # .omp e venv: junction para o principal (um estado so de tarefas/progresso); .env: copia.
    foreach ($dir in '.omp', 'venv') {
        if (-not (Test-Path "$wt/$dir")) { New-Item -ItemType Junction -Path "$wt/$dir" -Target "$root/$dir" | Out-Null }
    }
    if (Test-Path "$root/.env") { Copy-Item "$root/.env" "$wt/.env" }
    if ($Agent) { orca terminal create --worktree "path:$wt" --title $name --command $Agent --json | Out-Null }
    Write-Host "+ $name -> $wt ($estado)"
}
