<?php
declare(strict_types=1);

require_once __DIR__ . '/../lib/common.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
    exit;
}

$body = read_json_body();
$text = trim((string)($body['text'] ?? ''));
$voice = safe_token((string)($body['voice'] ?? 'femalenord'), 'voice');
$language = trim((string)($body['language'] ?? ''));

if ($text === '' || strlen($text) > 1200) {
    json_response(['ok' => false, 'error' => 'invalid_text'], 400);
    exit;
}

$payload = ['text' => $text, 'speaker_wav' => $voice];
if ($language !== '') {
    $payload['language'] = safe_token($language, 'language');
}

$context = stream_context_create([
    'http' => [
        'method' => 'POST',
        'header' => "Content-Type: application/json\r\n",
        'content' => json_encode($payload, JSON_UNESCAPED_UNICODE),
        'timeout' => 180,
        'ignore_errors' => true,
    ],
]);
$audio = @file_get_contents(OMNIVOICE_SERVICE_URL . '/tts_to_audio', false, $context);
if ($audio === false || $audio === '') {
    json_response(['ok' => false, 'error' => 'synthesis_failed'], 502);
    exit;
}

header('Content-Type: audio/wav');
header('Cache-Control: no-store');
echo $audio;
