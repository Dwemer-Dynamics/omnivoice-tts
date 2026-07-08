<?php
declare(strict_types=1);

require_once __DIR__ . '/../lib/common.php';

$root = omnivoice_root();
$health = fetch_json(OMNIVOICE_SERVICE_URL . '/health');
$provider = fetch_json(OMNIVOICE_SERVICE_URL . '/provider_info');
$config = read_json_file($root . '/config.json');
$diagnostics = read_json_file($root . '/diagnostics/latest.json');

json_response([
    'ok' => true,
    'root' => $root,
    'service_url' => OMNIVOICE_SERVICE_URL,
    'running' => is_array($health) && (($health['status'] ?? '') === 'ok'),
    'health' => $health,
    'provider' => $provider,
    'config' => $config,
    'diagnostics' => $diagnostics,
    'web_user' => get_current_user(),
]);
