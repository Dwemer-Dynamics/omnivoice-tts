<?php
declare(strict_types=1);

require_once __DIR__ . '/lib/common.php';
$root = omnivoice_root();
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OmniVoice TTS</title>
    <link rel="stylesheet" href="assets/omnivoice.css">
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
            <button id="startService" type="button">Start</button>
        </div>
    </header>

    <main class="layout">
        <section class="panel status-grid" aria-label="Status">
            <div>
                <span class="label">Service</span>
                <strong id="serviceState">Checking</strong>
            </div>
            <div>
                <span class="label">Startup</span>
                <strong id="startupState">Checking</strong>
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
                <strong>127.0.0.1:8021</strong>
            </div>
        </section>

        <section class="panel">
            <div class="section-head">
                <h2>Language</h2>
                <button id="loadLanguages" type="button">Reload</button>
            </div>
            <div class="form-row">
                <input id="languageSearch" type="search" placeholder="Search presets">
                <select id="presetSelect"></select>
                <label class="check"><input id="allowPlaceholder" type="checkbox"> Allow placeholder</label>
            </div>
            <div class="button-row">
                <button id="enablePreset" type="button">Enable Preset</button>
                <button id="setActive" type="button">Set Active</button>
                <button id="enableStartup" type="button">Enable Startup</button>
                <button id="disableStartup" type="button">Disable Startup</button>
            </div>
            <div id="languageMeta" class="meta-line"></div>
        </section>

        <section class="panel">
            <div class="section-head">
                <h2>Voice Library</h2>
                <button id="refreshVoices" type="button">Audit</button>
            </div>
            <div class="form-row compact">
                <input id="voiceId" type="text" value="femalenord" placeholder="VoiceID">
                <button id="importVoice" type="button">Import</button>
                <button id="calibrateVoice" type="button">Calibrate</button>
                <button id="buildVoice" type="button">Build One</button>
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

        <section class="panel">
            <div class="section-head">
                <h2>Jobs</h2>
                <button id="refreshJobs" type="button">Refresh Jobs</button>
            </div>
            <div id="jobList" class="job-list"></div>
            <pre id="jobLog" class="job-log"></pre>
        </section>
    </main>

    <footer>
        <span>Root: <?php echo htmlspecialchars($root, ENT_QUOTES, 'UTF-8'); ?></span>
    </footer>

    <script src="assets/omnivoice.js"></script>
</body>
</html>
