<?php
  /*
   All Emoncms code is released under the GNU Affero General Public License.
   See COPYRIGHT.txt and LICENSE.txt.

    ---------------------------------------------------------------------
    Emoncms - open source energy visualisation
    Part of the OpenEnergyMonitor project:
    http://openenergymonitor.org
  */

// no direct access
defined('EMONCMS_EXEC') or die('Restricted access');

// Retained, so the service gets the latest copy whenever it (re)connects
function hpctrl_publish($topic, $payload)
{
    global $settings;
    if (!class_exists('Mosquitto\\Client')) return false;
    try {
        $client = new Mosquitto\Client();
        $client->setCredentials($settings['mqtt']['user'],$settings['mqtt']['password']);
        $client->connect($settings['mqtt']['host'], $settings['mqtt']['port'], 5);
        $client->publish($topic, json_encode($payload), 0, true);
    } catch (Exception $e) {
        return false;
    }
    return true;
}

function hpctrl_controller()
{
    global $mysqli, $redis, $session, $route, $settings;

    $result = false;
    
    require __DIR__."/hpctrl_ui_settings.php";
    
    if (!$session['write']) return false;
    if (!in_array($session['userid'],$hpctrl_users)) return false;
    
    if ($route->action == '' && $session['write']) {
        require "Modules/hpctrl/hpctrl_model.php";
        $hpctrl = new HPCtrl($mysqli);
        return view("Modules/hpctrl/Views/hpctrl_view.php",array(
            'dhw_enable'=>$dhw_enable,
            'settings'=>$hpctrl->get_settings($session['userid'])
        ));
    }

    if ($route->action == 'get-config' && $session['read']) {
        $route->format = "json";
        require "Modules/hpctrl/hpctrl_model.php";
        $hpctrl = new HPCtrl($mysqli);
        return $hpctrl->get($session['userid']);
    }

    if ($route->action == 'set-settings' && $session['write']) {
        $route->format = "json";
        $ui_settings = json_decode(post('settings'));
        if (!is_object($ui_settings)) return array("success"=>false, "message"=>"Invalid settings");
        require "Modules/hpctrl/hpctrl_model.php";
        $hpctrl = new HPCtrl($mysqli);
        if (!$hpctrl->set_settings($session['userid'],$ui_settings)) return array("success"=>false);

        // Control inputs, published only once this user has chosen some,
        // so another user saving their dial settings can't clear them
        $inputs = array();
        $chosen = false;
        foreach ($hpctrl->get_settings($session['userid']) as $key=>$value) {
            if (strpos($key,'in_')!==0) continue;
            $chosen = true;
            if ($value>0) $inputs[substr($key,3)] = (int) $value;
        }
        if ($chosen && $mqtt_enable && !hpctrl_publish("hpctrl/inputs", (object) $inputs)) {
            return array("success"=>false, "message"=>"Saved, but not sent to the service");
        }
        return array("success"=>true);
    }

    // Service status and recent events, written to Redis by service/hpctrl.py
    if ($route->action == 'status' && $session['read']) {
        $route->format = "json";
        if (!$redis) return array("success"=>false, "message"=>"Redis not available");
        $status = json_decode((string) $redis->get("hpctrl:status"));
        $events = array();
        foreach ($redis->lRange("hpctrl:events", 0, 49) as $event) $events[] = json_decode($event);
        return array("success"=>true, "time"=>time(), "status"=>$status, "events"=>$events);
    }

    if ($route->action == 'set-config' && $session['write']) {
        $route->format = "json";
        if (isset($_POST['config'])) {
            $config = json_decode($_POST['config']);
            if ($config) {                
                require "Modules/hpctrl/hpctrl_model.php";
                $hpctrl = new HPCtrl($mysqli);
                $hpctrl->set($session['userid'],$config);
                
                if ($mqtt_enable && !hpctrl_publish("hpctrl/config", $config)) {
                    return array("success"=>false, "message"=>"Saved, but not sent to the service");
                }
                return array("success"=>"true");
            }        
        }
    }

    return array('content'=>$result);
}
