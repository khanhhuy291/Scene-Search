param(
    [string]$ModelRoot = 'E:\SceneSearchData\temporal-search',
    [string]$Queries = '',
    [ValidatePattern('^[A-Za-z0-9_-]{1,80}$')]
    [string]$RunName = ('grounding-cpu-rerun-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$researchRoot = (Resolve-Path -LiteralPath $ModelRoot).Path
if ([string]::IsNullOrWhiteSpace($Queries)) {
    $Queries = Join-Path $PSScriptRoot 'evaluation/pilot.provisional.jsonl'
}
$queryFile = (Resolve-Path -LiteralPath $Queries).Path
$sourceLock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'research/source-lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$imageName = $sourceLock.legacy_base_image.tag
$imageId = (& docker image inspect $imageName --format '{{.Id}}').Trim()
if ($LASTEXITCODE -ne 0 -or $imageId -ne $sourceLock.legacy_base_image.image_id) {
    throw 'The local image differs from the verified research image. Review source-lock.json before rerunning.'
}
foreach ($sourceName in @('lighthouse', 'openai_clip')) {
    $sourceEntry = $sourceLock.code.$sourceName
    $sourcePath = Join-Path $repositoryRoot $sourceEntry.local_path
    $sourceRevision = (& git -C $sourcePath rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceRevision -ne $sourceEntry.commit) {
        throw "Research source revision mismatch: $sourceName"
    }
}
$outputRoot = Join-Path $repositoryRoot 'data/temporal-search/group-b'
$runOutput = Join-Path $outputRoot $RunName
if (Test-Path -LiteralPath $runOutput) {
    throw 'The output directory already exists. Choose another RunName to preserve earlier results.'
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$dockerArguments = @(
    'run', '--rm', '--cpus', '2', '--memory', '1g', '--memory-swap', '2g', '--network', 'none',
    '--mount', "type=bind,source=$researchRoot\runtime,target=/runtime,readonly",
    '--mount', "type=bind,source=$researchRoot\models,target=/models,readonly",
    '--mount', "type=bind,source=$repositoryRoot\data\research\lighthouse,target=/lighthouse,readonly",
    '--mount', "type=bind,source=$repositoryRoot\data\research\openai-clip,target=/clip-source,readonly",
    '--mount', "type=bind,source=$PSScriptRoot,target=/experiment,readonly",
    '--mount', "type=bind,source=$queryFile,target=/queries.jsonl,readonly",
    '--mount', "type=bind,source=$repositoryRoot\data\rawdata,target=/rawdata,readonly",
    '--mount', "type=bind,source=$outputRoot,target=/output",
    '--env', 'PYTHONPATH=/runtime:/lighthouse:/clip-source',
    '--entrypoint', 'python', $imageName, '/experiment/tools/run_grounding_pilot.py',
    '--queries', '/queries.jsonl', '--raw-root', '/rawdata',
    '--models', '/models', '--output', "/output/$RunName", '--device', 'cpu', '--image-batch-size', '1'
)
& docker @dockerArguments
if ($LASTEXITCODE -ne 0) {
    throw "Checkpoint pilot exited with code $LASTEXITCODE"
}
Write-Output "Results: $runOutput"
