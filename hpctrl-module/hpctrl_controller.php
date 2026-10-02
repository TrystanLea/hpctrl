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

// Retained by default, so the service gets the latest copy whenever it (re)connects
function hpctrl_publish($topic, $payload, $retain = true)
{
    global $settings;
    if (!class_exists('Mosquitto\\Client')) return false;
    try {
        $client = new Mosquitto\Client();
        $client->setCredentials($settings['mqtt']['user'],$settings['mqtt']['password']);
        $client->connect($settings['mqtt']['host'], $settings['mqtt']['port'], 5);
        $client->publish($topic, json_encode($payload), 0, $retain);
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

        // Sensor feeds for the service, sent when the UI changes a sensor: setting key => service role
        if (post('publish_sensors')) {
            $roles = array('room'=>'room','flow'=>'flow','return'=>'return','flowrate'=>'flowrate',
                'cyl_top'=>'cyl_top','cyl_bot'=>'cyl_bot','outside'=>'ambient','extpipe'=>'extpipe');
            $sensors = array();
            foreach ($hpctrl->get_settings($session['userid']) as $key=>$value) {
                if (isset($roles[$key]) && $value>0) $sensors[$roles[$key]] = (int) $value;
            }
            if (!$mqtt_enable || !hpctrl_publish("hpctrl/sensors", (object) $sensors)) {
                return array("success"=>false, "message"=>"Saved, but not sent to the service");
            }
        }
        return array("success"=>true);
    }

    // Control parameters for the service, which checks their ranges. Empty resets to defaults.
    if ($route->action == 'set-params' && $session['write']) {
        $route->format = "json";
        $params = json_decode(post('params'));
        if (!is_object($params)) return array("success"=>false, "message"=>"Invalid parameters");
        $clean = array();
        foreach ($params as $key=>$value) {
            if (preg_match('/^[a-z0-9_]+$/',$key) && is_numeric($value)) $clean[$key] = $value + 0;
        }
        if (!$mqtt_enable || !hpctrl_publish("hpctrl/params", (object) $clean)) {
            return array("success"=>false, "message"=>"Not sent to the service");
        }
        return array("success"=>true);
    }

    // Manual commands: not retained, and the service ignores them after a minute
    if ($route->action == 'command' && $session['write']) {
        $route->format = "json";
        $cmd = post('cmd');
        if (!in_array($cmd, array('dhw_start','dhw_stop'))) return array("success"=>false, "message"=>"Unknown command");
        if (!$mqtt_enable || !hpctrl_publish("hpctrl/command", array("cmd"=>$cmd, "time"=>time()), false)) {
            return array("success"=>false, "message"=>"Not sent to the service");
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
