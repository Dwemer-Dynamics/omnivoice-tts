<?php
declare(strict_types=1);

require_once __DIR__ . '/lib/common.php';
$root = omnivoice_root();
$assetVersion = static function (string $path): string {
    $fullPath = __DIR__ . '/' . ltrim($path, '/');
    $version = is_file($fullPath) ? (string)filemtime($fullPath) : (string)time();
    return $path . '?v=' . rawurlencode($version);
};
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OmniVoice TTS</title>
    <link rel="stylesheet" href="<?php echo htmlspecialchars($assetVersion('assets/omnivoice.css'), ENT_QUOTES, 'UTF-8'); ?>">
</head>
<body>
    <header class="topbar">
        <div>
            <h1>OmniVoice TTS</h1>
            <p>DwemerDistro multilingual voice control panel</p>
        </div>
        <div class="top-actions">
            <button id="refreshStatus" type="button">Refresh</button>
            <button id="runDoctor" type="button">Run Doctor</button>
        </div>
    </header>

    <main class="layout">
        <section class="panel status-grid" aria-label="Status">
            <div>
                <span class="label">Service</span>
                <strong id="serviceState">Checking</strong>
            </div>
            <div>
                <span class="label">Language</span>
                <strong id="activeLanguage">Unknown</strong>
            </div>
            <div>
                <span class="label">Voices</span>
                <strong id="voiceCount">0</strong>
            </div>
            <div>
                <span class="label">GPU</span>
                <strong id="gpuName">Unknown</strong>
            </div>
            <div>
                <span class="label">Endpoint</span>
                <strong>0.0.0.0:8021 (LAN enabled)</strong>
            </div>
        </section>

        <section class="panel primary-panel">
            <div class="section-head">
                <h2>Installed Language</h2>
                <button id="loadLanguages" type="button">Reload</button>
            </div>
            <div class="form-row">
                <select id="profileSelect"></select>
                <button id="setActive" type="button">Set Active</button>
                <button id="refreshVoices" type="button">Audit Voices</button>
            </div>
            <div id="languageMeta" class="meta-line"></div>
        </section>

        <section class="panel">
            <div class="section-head">
                <h2>Voice Library</h2>
                <span id="libraryLanguage" class="meta-line"></span>
            </div>
            <div class="form-row compact">
                <input id="voiceId" type="text" value="femalenord" placeholder="VoiceID">
                <button id="calibrateVoice" type="button">Prepare Voice</button>
                <button id="buildVoice" type="button">Build Voice</button>
                <button id="buildFull" class="danger" type="button">Build Full Library</button>
            </div>
            <div class="voice-summary" id="voiceSummary">No audit loaded.</div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>VoiceID</th>
                            <th>Status</th>
                            <th>Calibrated</th>
                            <th>Warnings</th>
                        </tr>
                    </thead>
                    <tbody id="voiceRows"></tbody>
                </table>
            </div>
        </section>

        <section class="panel">
            <div class="section-head">
                <h2>Test Voice</h2>
            </div>
            <textarea id="testText" rows="3">Hola, esta es una prueba de voz en espanol.</textarea>
            <div class="form-row compact">
                <input id="testVoice" type="text" value="femalenord" placeholder="VoiceID">
                <button id="generateTest" type="button">Generate</button>
                <audio id="audioPlayer" controls></audio>
            </div>
        </section>
    </main>

    <footer>
        <span>Original tool by ErikErix (Discord) / erikholik (NexusMods)</span>
        <span>Root: <?php echo htmlspecialchars($root, ENT_QUOTES, 'UTF-8'); ?></span>
    </footer>

    <script src="<?php echo htmlspecialchars($assetVersion('assets/omnivoice.js'), ENT_QUOTES, 'UTF-8'); ?>"></script>
</body>
</html>
