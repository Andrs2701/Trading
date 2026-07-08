# Ejecutar backtests paralelos para ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT
# Cada uno corre base + HMM + funnel

$assets = @("ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT")
$jobs = @()

Write-Host "[FASE-C] Lanzando backtests paralelos para 4 activos..." -ForegroundColor Cyan

foreach ($asset in $assets) {
    $csv = "$($asset.ToLower())_m5.csv"
    $job = Start-Job -ScriptBlock {
        param($asset, $csv)
        $ErrorActionPreference = "Stop"
        Set-Location "C:\Users\camilo.chitiva\Trading\code\python"

        try {
            Write-Host "[backtest $asset] Iniciando base..."
            & python satar_backtest.py --csv $csv --trail I | Out-File "backtest_${asset}_base.log" -Append
            Rename-Item -Path "trades_out.csv" -NewName "trades_${asset}_base.csv" -Force

            Write-Host "[backtest $asset] Iniciando HMM..."
            & python satar_backtest.py --csv $csv --trail I --hmm | Out-File "backtest_${asset}_hmm.log" -Append
            Rename-Item -Path "trades_out.csv" -NewName "trades_${asset}_hmm.csv" -Force

            Write-Host "[backtest $asset] Iniciando funnel..."
            & python satar_backtest.py --csv $csv --trail I --funnel | Out-File "backtest_${asset}_funnel.log" -Append

            # El funnel genera un JSON, moverlo
            if (Test-Path "results\funnel.json") {
                Copy-Item "results\funnel.json" -Destination "funnel_${asset}.json" -Force
            }

            Write-Host "[backtest $asset] COMPLETADO" -ForegroundColor Green
        }
        catch {
            Write-Host "[backtest $asset] ERROR: $_" -ForegroundColor Red
            throw $_
        }
    } -ArgumentList $asset, $csv

    $jobs += $job
    Write-Host "[FASE-C] Job lanzado para $asset (ID: $($job.Id))" -ForegroundColor Cyan
}

Write-Host "[FASE-C] Todos los jobs lanzados. Esperando resultados..." -ForegroundColor Yellow
Write-Host "Jobs en ejecución:"
$jobs | Select-Object -Property Id, Name, State

# Esperar a que terminen todos
$completed = 0
while ($jobs.Count -gt 0) {
    $jobs = $jobs | Where-Object { $_.State -eq "Running" }
    if ($jobs.Count -eq 0) {
        Write-Host "[FASE-C] Todos los backtests completados." -ForegroundColor Green
        break
    }
    Write-Host "[FASE-C] Aún hay $($jobs.Count) jobs en ejecución..." -ForegroundColor Yellow
    Start-Sleep -Seconds 30
}
