<?php

require __DIR__."/hpctrl_ui_settings.php";

if ($session['write'] && in_array($session['userid'],$hpctrl_users)) {
    $menu["hpctrl"] = array("name"=>"hpctrl", "order"=>3, "icon"=>"hpmon", "href"=>"hpctrl");
}
