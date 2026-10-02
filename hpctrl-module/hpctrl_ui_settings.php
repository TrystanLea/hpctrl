<?php
// Load install specific UI settings, falling back to the tracked defaults.
// __DIR__ resolves the Modules/hpctrl symlink to the repo's hpctrl-module directory.
$hpctrl_ui_settings = __DIR__."/../config/ui_settings.php";
if (!file_exists($hpctrl_ui_settings)) $hpctrl_ui_settings = __DIR__."/../config/ui_settings.default.php";
require $hpctrl_ui_settings;
