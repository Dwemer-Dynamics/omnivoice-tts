<?php
declare(strict_types=1);

const OMNIVOICE_SERVICE_URL = 'http://127.0.0.1:8021';

function omnivoice_root(): string
{
    $candidates = [];
    $envRoot = getenv('OMNIVOICE_ROOT');
    if (is_string($envRoot) && $envRoot !== '') {
        $candidates[] = $envRoot;
    }
    $candidates[] = dirname(__DIR__, 2);
    $realWeb = realpath(__DIR__ . '/..');
    if (is_string($realWeb)) {
        $candidates[] = dirname($realWeb);
    }
    $candidates[] = '/home/dwemer/omnivoice-tts';

    foreach ($candidates as $candidate) {
        $root = realpath($candidate);
        if (is_string($root) && is_file($root . '/omnivoice_cli.py')) {
            return $root;
        }
    }

    return '/home/dwemer/omnivoice-tts';
}

function json_response(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
}

function read_json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        return [];
    }
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        json_response(['ok' => false, 'error' => 'invalid_json'], 400);
        exit;
    }
    return $data;
}

function read_json_file(string $path): ?array
{
    if (!is_file($path)) {
        return null;
    }
    $raw = file_get_contents($path);
    if ($raw === false) {
        return null;
    }
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}

function fetch_json(string $url, float $timeout = 4.0): ?array
{
    $context = stream_context_create([
        'http' => [
            'method' => 'GET',
            'timeout' => $timeout,
            'ignore_errors' => true,
        ],
    ]);
    $raw = @file_get_contents($url, false, $context);
    if ($raw === false) {
        return null;
    }
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}

function post_json(string $url, array $payload, float $timeout = 30.0): array
{
    $context = stream_context_create([
        'http' => [
            'method' => 'POST',
            'header' => "Content-Type: application/json\r\n",
            'content' => json_encode($payload, JSON_UNESCAPED_UNICODE),
            'timeout' => $timeout,
            'ignore_errors' => true,
        ],
    ]);
    $raw = @file_get_contents($url, false, $context);
    if ($raw === false) {
        return ['ok' => false, 'error' => 'request_failed'];
    }
    $decoded = json_decode($raw, true);
    return [
        'ok' => is_array($decoded),
        'body' => is_array($decoded) ? $decoded : null,
        'raw' => is_array($decoded) ? null : $raw,
    ];
}

function shell_join(array $parts): string
{
    return implode(' ', array_map('escapeshellarg', $parts));
}

function python_bin(string $root): string
{
    $venvPython = $root . '/venv/bin/python';
    return is_executable($venvPython) ? $venvPython : 'python3';
}

function run_cli(array $args, int $timeout = 60): array
{
    $root = omnivoice_root();
    $command = shell_join(array_merge([python_bin($root), 'omnivoice_cli.py'], $args));
    $descriptor = [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ];
    $process = proc_open($command, $descriptor, $pipes, $root);
    if (!is_resource($process)) {
        return ['ok' => false, 'exit_code' => 127, 'stdout' => '', 'stderr' => 'Unable to start process.'];
    }
    fclose($pipes[0]);
    stream_set_blocking($pipes[1], false);
    stream_set_blocking($pipes[2], false);

    $stdout = '';
    $stderr = '';
    $started = time();
    $observedExitCode = null;
    while (true) {
        $status = proc_get_status($process);
        $stdout .= stream_get_contents($pipes[1]);
        $stderr .= stream_get_contents($pipes[2]);
        if (!$status['running']) {
            if (isset($status['exitcode']) && (int)$status['exitcode'] >= 0) {
                $observedExitCode = (int)$status['exitcode'];
            }
            break;
        }
        if ((time() - $started) > $timeout) {
            proc_terminate($process);
            foreach ($pipes as $pipe) {
                if (is_resource($pipe)) {
                    fclose($pipe);
                }
            }
            proc_close($process);
            return ['ok' => false, 'exit_code' => 124, 'stdout' => $stdout, 'stderr' => 'Timed out.'];
        }
        usleep(100000);
    }
    foreach ($pipes as $pipe) {
        if (is_resource($pipe)) {
            fclose($pipe);
        }
    }
    $exitCode = proc_close($process);
    if ($exitCode < 0 && $observedExitCode !== null) {
        $exitCode = $observedExitCode;
    }
    return ['ok' => $exitCode === 0, 'exit_code' => $exitCode, 'stdout' => $stdout, 'stderr' => $stderr];
}

function safe_token(string $value, string $name, int $maxLength = 80): string
{
    $value = trim($value);
    if ($value === '' || strlen($value) > $maxLength || !preg_match('/^[A-Za-z0-9_. -]+$/', $value)) {
        json_response(['ok' => false, 'error' => 'invalid_' . $name], 400);
        exit;
    }
    return $value;
}

function jobs_dir(): string
{
    $dir = omnivoice_root() . '/diagnostics/web_jobs';
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    return $dir;
}

function job_payload(string $jobId): ?array
{
    if (!preg_match('/^[A-Za-z0-9_-]+$/', $jobId)) {
        return null;
    }
    $dir = jobs_dir() . '/' . $jobId;
    $meta = read_json_file($dir . '/job.json');
    if ($meta === null) {
        return null;
    }
    $exitPath = $dir . '/exit_code';
    if (is_file($exitPath)) {
        $exitCode = (int)trim((string)file_get_contents($exitPath));
        $meta['state'] = $exitCode === 0 ? 'completed' : 'failed';
        $meta['exit_code'] = $exitCode;
    } else {
        $meta['state'] = 'running';
    }
    $log = is_file($dir . '/job.log') ? file_get_contents($dir . '/job.log') : '';
    $meta['log_tail'] = substr((string)$log, -12000);
    return $meta;
}

function start_job(string $label, array $commands): array
{
    $root = omnivoice_root();
    $jobsRoot = jobs_dir();
    $cacheRoot = $root . '/model_cache';
    foreach ([$cacheRoot, $cacheRoot . '/huggingface', $cacheRoot . '/huggingface/hub'] as $cacheDir) {
        if (!is_dir($cacheDir)) {
            @mkdir($cacheDir, 0777, true);
        }
        @chmod($cacheDir, 0777);
    }
    $jobId = gmdate('YmdHis') . '-' . bin2hex(random_bytes(4));
    $dir = $jobsRoot . '/' . $jobId;
    if (!mkdir($dir, 0775, true) && !is_dir($dir)) {
        return ['ok' => false, 'error' => 'job_dir_failed'];
    }

    $script = "#!/usr/bin/env bash\n";
    $script .= "set -u\n";
    $script .= "umask 0000\n";
    $script .= "cd " . escapeshellarg($root) . "\n";
    $script .= "export HOME=" . escapeshellarg($root) . "\n";
    $script .= "export XDG_CACHE_HOME=" . escapeshellarg($cacheRoot) . "\n";
    $script .= "export HF_HOME=" . escapeshellarg($cacheRoot . '/huggingface') . "\n";
    $script .= "export HUGGINGFACE_HUB_CACHE=" . escapeshellarg($cacheRoot . '/huggingface/hub') . "\n";
    $script .= "export TRANSFORMERS_CACHE=" . escapeshellarg($cacheRoot . '/huggingface/hub') . "\n";
    $script .= "export PYTHONUTF8=1\n";
    $script .= "export PYTHONIOENCODING=utf-8\n";
    $script .= "echo \"Started: $(date -Is)\"\n";
    $script .= "code=0\n";
    foreach ($commands as $command) {
        $script .= "echo\n";
        $script .= "echo " . escapeshellarg('$ ' . implode(' ', $command)) . "\n";
        $script .= shell_join($command) . "\n";
        $script .= "code=$?\n";
        $script .= "if [ \"\$code\" -ne 0 ]; then\n";
        $script .= "  echo\n";
        $script .= "  echo \"Command failed: exit=\$code\"\n";
        $script .= "  echo \"Finished: $(date -Is) exit=\$code\"\n";
        $script .= "  echo \"\$code\" > " . escapeshellarg($dir . '/exit_code') . "\n";
        $script .= "  exit \"\$code\"\n";
        $script .= "fi\n";
    }
    $script .= "echo\n";
    $script .= "echo \"Finished: $(date -Is) exit=\$code\"\n";
    $script .= "echo \"\$code\" > " . escapeshellarg($dir . '/exit_code') . "\n";
    $script .= "exit \"\$code\"\n";
    file_put_contents($dir . '/job.sh', $script);
    chmod($dir . '/job.sh', 0755);

    $meta = [
        'id' => $jobId,
        'label' => $label,
        'state' => 'running',
        'created_at_utc' => gmdate('c'),
        'commands' => $commands,
    ];
    file_put_contents($dir . '/job.json', json_encode($meta, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) . "\n");

    $launch = 'nohup bash ' . escapeshellarg($dir . '/job.sh') . ' > ' . escapeshellarg($dir . '/job.log') . ' 2>&1 & echo $!';
    $pid = trim((string)shell_exec($launch));
    $meta['pid'] = $pid;
    file_put_contents($dir . '/job.json', json_encode($meta, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) . "\n");

    return ['ok' => true, 'job' => job_payload($jobId)];
}
