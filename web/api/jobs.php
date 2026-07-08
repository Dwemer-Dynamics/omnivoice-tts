<?php
declare(strict_types=1);

require_once __DIR__ . '/../lib/common.php';

$root = omnivoice_root();
$python = python_bin($root);

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $id = (string)($_GET['id'] ?? '');
    if ($id !== '') {
        $job = job_payload($id);
        json_response(['ok' => $job !== null, 'job' => $job], $job !== null ? 200 : 404);
        exit;
    }

    $jobs = [];
    foreach (array_reverse(glob(jobs_dir() . '/*', GLOB_ONLYDIR) ?: []) as $dir) {
        $job = job_payload(basename($dir));
        if ($job !== null) {
            $jobs[] = $job;
        }
        if (count($jobs) >= 20) {
            break;
        }
    }
    json_response(['ok' => true, 'jobs' => $jobs]);
    exit;
}

$body = read_json_body();
$action = (string)($body['action'] ?? '');
$commands = [];
$label = '';

if ($action === 'enable_startup') {
    $commands[] = ['ln', '-sf', $root . '/start-gpu.sh', $root . '/start.sh'];
    $commands[] = ['chmod', '+x', $root . '/start-gpu.sh', $root . '/start.sh'];
    $label = 'Enable OmniVoice startup';
} elseif ($action === 'disable_startup') {
    $commands[] = ['rm', '-f', $root . '/start.sh'];
    $label = 'Disable OmniVoice startup';
} elseif ($action === 'start_service') {
    $commands[] = [$root . '/start-gpu.sh'];
    $label = 'Start OmniVoice service';
} elseif ($action === 'doctor') {
    $commands[] = [$python, 'omnivoice_cli.py', 'doctor', '--json', 'diagnostics/latest.json'];
    $label = 'Run doctor';
} elseif ($action === 'verify') {
    $language = safe_token((string)($body['language'] ?? ''), 'language');
    $commands[] = [$python, 'omnivoice_cli.py', 'verify', '--language', $language, '--write-library-report'];
    $label = 'Verify ' . $language;
} elseif ($action === 'import_voice') {
    $language = safe_token((string)($body['language'] ?? ''), 'language');
    $voice = safe_token((string)($body['voice'] ?? ''), 'voice');
    $commands[] = [$python, 'omnivoice_cli.py', 'import-chim', '--language', $language, '--voice', $voice];
    $label = 'Import ' . $voice . ' for ' . $language;
} elseif ($action === 'calibrate_voice') {
    $language = safe_token((string)($body['language'] ?? ''), 'language');
    $voice = safe_token((string)($body['voice'] ?? ''), 'voice');
    $commands[] = [$python, 'omnivoice_cli.py', 'import-chim', '--language', $language, '--voice', $voice];
    $commands[] = [$python, 'omnivoice_cli.py', 'calibrate', '--language', $language, '--voice', $voice];
    $label = 'Prepare and calibrate ' . $voice . ' for ' . $language;
} elseif ($action === 'build_voice') {
    $language = safe_token((string)($body['language'] ?? ''), 'language');
    $voice = safe_token((string)($body['voice'] ?? ''), 'voice');
    $commands[] = [$python, 'omnivoice_cli.py', 'import-chim', '--language', $language, '--voice', $voice];
    $commands[] = [$python, 'omnivoice_cli.py', 'build-library', '--language', $language, '--voice', $voice];
    $label = 'Build ' . $voice . ' for ' . $language;
} elseif ($action === 'build_full') {
    $language = safe_token((string)($body['language'] ?? ''), 'language');
    $commands[] = [$python, 'omnivoice_cli.py', 'import-chim', '--language', $language, '--all'];
    $commands[] = [$python, 'omnivoice_cli.py', 'build-library', '--language', $language, '--all'];
    $label = 'Build full library for ' . $language;
} else {
    json_response(['ok' => false, 'error' => 'unknown_action'], 400);
    exit;
}

json_response(start_job($label, $commands));
