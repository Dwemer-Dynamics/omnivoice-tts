<?php
declare(strict_types=1);

require_once __DIR__ . '/../lib/common.php';

$root = omnivoice_root();
$config = read_json_file($root . '/config.json') ?: [];
$language = safe_token((string)($_GET['language'] ?? ($config['active_language'] ?? 'sk')), 'language');
$refresh = (string)($_GET['refresh'] ?? '') === '1';

$result = null;
if ($refresh) {
    $result = run_cli(['voices', '--language', $language, '--write-report'], 120);
}

$reportPath = $root . '/reports/' . $language . '/library_audit.json';
$report = read_json_file($reportPath);

json_response([
    'ok' => $report !== null,
    'language' => $language,
    'report_path' => $reportPath,
    'report' => $report,
    'refresh_result' => $result,
]);
