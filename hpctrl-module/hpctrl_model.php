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

class HPCtrl
{
    private $mysqli;

    public function __construct($mysqli) 
    {
        $this->mysqli = $mysqli;
    }
    
    public function set($userid,$config)
    {
        $userid = (int) $userid;
        $config = json_encode($config);
        $config = preg_replace('/[^\w\s\-.",:#&{}\[\]]/','',$config);
        
        if (!$result = $this->mysqli->query("SELECT config FROM hpctrl WHERE `userid`='$userid'")) {
            return false;
        }
        if ($result->num_rows) {
            $stmt = $this->mysqli->prepare("UPDATE hpctrl SET `config`=? WHERE `userid`=?");
            $stmt->bind_param("si", $config, $userid);
            if (!$stmt->execute()) return false;
        } else {
            $stmt = $this->mysqli->prepare("INSERT INTO hpctrl ( userid, config ) VALUES (?,?)");
            $stmt->bind_param("is", $userid, $config);
            if (!$stmt->execute()) return false;
        }
        return true;
    }
    
    // UI settings: feed ids for live values, the dial range, and in_* emoncms input ids read by the service
    private $setting_keys = array('room','flow','outside','elec','heat','dial_min','dial_max','dial_step',
        'in_room','in_flow','in_return','in_flowrate','in_cyl_top','in_cyl_bot','in_ambient','in_extpipe');

    public function set_settings($userid,$settings)
    {
        $userid = (int) $userid;
        $clean = array();
        foreach ($this->setting_keys as $key) {
            if (isset($settings->$key) && is_numeric($settings->$key)) $clean[$key] = $settings->$key + 0;
        }
        $settings = json_encode($clean);

        if (!$result = $this->mysqli->query("SELECT userid FROM hpctrl WHERE `userid`='$userid'")) {
            return false;
        }
        if ($result->num_rows) {
            $stmt = $this->mysqli->prepare("UPDATE hpctrl SET `settings`=? WHERE `userid`=?");
            $stmt->bind_param("si", $settings, $userid);
        } else {
            $stmt = $this->mysqli->prepare("INSERT INTO hpctrl ( userid, settings ) VALUES (?,?)");
            $stmt->bind_param("is", $userid, $settings);
        }
        return $stmt->execute();
    }

    public function get_settings($userid)
    {
        $userid = (int) $userid;
        if ($result = $this->mysqli->query("SELECT settings FROM hpctrl WHERE `userid`='$userid'")) {
            if ($row = $result->fetch_array()) {
                if ($settings = json_decode((string) $row['settings'])) return $settings;
            }
        }
        return new stdClass();
    }

    public function get($userid)
    {
        $userid = (int) $userid;
        if (!$result = $this->mysqli->query("SELECT config FROM hpctrl WHERE `userid`='$userid'")) {
            return false;
        }
        if ($result->num_rows) {
            $row = $result->fetch_array();
            $config = json_decode($row['config']);
            return $config;
        }
        return false;
    }
}
