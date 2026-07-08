<?php
declare(strict_types=1);

require_once __DIR__ . '/../lib/common.php';

$root = omnivoice_root();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $body = read_json_body();
    $action = (string)($body['action'] ?? '');

    if ($action === 'set_active') {
        $language = safe_token((string)($body['language'] ?? ''), 'language');
        $result = run_cli(['set-language', $language, '--live-if-running'], 60);
        json_response(['ok' => $result['ok'], 'result' => $result], $result['ok'] ? 200 : 500);
        exit;
    }

    json_response(['ok' => false, 'error' => 'unknown_action'], 400);
    exit;
}

$profiles = [];
foreach (glob($root . '/languages/*.json') ?: [] as $profilePath) {
    $profile = read_json_file($profilePath);
    if (is_array($profile)) {
        $hasTemplateText = str_contains((string)($profile['bootstrap_text'] ?? ''), 'REPLACE THIS')
            || str_contains((string)($profile['master_text'] ?? ''), 'REPLACE THIS');
        if ($hasTemplateText) {
            continue;
        }
        $profiles[] = [
            'id' => (string)($profile['id'] ?? basename($profilePath, '.json')),
            'display_name' => (string)($profile['display_name'] ?? basename($profilePath, '.json')),
            'omnivoice_language' => (string)($profile['omnivoice_language'] ?? ''),
            'whisper_language' => (string)($profile['whisper_language'] ?? ''),
        ];
    }
}

$config = read_json_file($root . '/config.json') ?: [];

json_response([
    'ok' => true,
    'active_language' => (string)($config['active_language'] ?? 'sk'),
    'profiles' => $profiles,
]);
