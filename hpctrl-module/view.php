<?php 
defined('EMONCMS_EXEC') or die('Restricted access');
global $path; 
$v=3; 
    
load_js("Lib/js/vue.global.prod-3.5.22.min.js");
load_css("Modules/hpctrl/style.css");
?>
    
<style>

#live td {
  text-align:center;
  width:25%;
}

.set_point {
  font-size:48px;
  padding:20px;
  display:inline-block
}

.room_temperature {
  margin-top:5px;
  margin-bottom:20px;
}
.set_point_ctrl {
  display:inline-block;
  padding:10px;
  font-size:48px;
}

[v-cloak] {
  display: none;
}


</style>
    
<div id="app" style="max-width:500px" v-cloak>


  <div class="saved hide">Saved</div>
  
  <div style="text-align:center">
    <h2>Heatpump Control</h2>
    <p>SET POINT</p>
    <div class="set_point_ctrl"><button @click="dec_set_point">-</button></div>
    <div class="set_point">{{ config.heating[active_period].set_point }}</div>
    <div class="set_point_ctrl"><button @click="inc_set_point">+</button></div>
    <div class="room_temperature">Temperature: {{ toFixed(room_temperature,1) }}&#8451;</div>
  </div>
  
  <table id="live" class="table">
    <tr>
    <td><b>Flow</b><br>{{ toFixed(flow_temperature,1) }}&#8451;</td>
    <td><b>Outside</b><br>{{ toFixed(outside_temperature,1) }}&#8451;</td>
    <td><b>Elec</b><br>{{ toFixed(heatpump_elec,0) }}W</td>
    <td><b>Heat</b><br>{{ toFixed(heatpump_heat,0) }}W</td>
    </tr>
  </table>
  
  <div style="float:right">{{ time }}</div>
  
  <h3>Space Heating</h3>
  <table class="table">
    <tr><th>Time</th><th>Set point</th><th>FlowT</th><th>Mode</th><th><button class="btn" @click="add_space"><i class="icon-plus"></i></button></th></tr>
    <tr v-for="(item,index) in config.heating" v-bind:class="{ warning: index==active_period }">
      <td><input type="text" v-model="item.start" @change="save"/></td>
      <td><input type="text" v-model.number="item.set_point" @change="save"/></td>
      <td><input type="text" v-model.number="item.flowT" @change="save"/></td>
      <td><select v-model="item.mode" @change="save">
        <option>min</option>
        <option>max</option>
      </select></td>
      <td><button class="btn"  @click="delete_space(index)"><i class="icon-trash"></i></button></td> 
    </tr>
  </table>

  <?php if (isset($dhw_enable) && $dhw_enable) { ?>
  <h3>DHW</h3>
  <table class="table">
    <tr><th>Start</th><th>Target</th><th>FlowT</th><th></th><th><button class="btn" @click="add_dhw"><i class="icon-plus"></i></button></th></tr>
    <tr v-for="(item,index) in config.dhw">
      <td><input type="text" v-model="item.start" @change="save"/></td>
      <td><input type="text" v-model.number="item.T" @change="save"/></td>
      <td><input type="text" v-if="item.mode=='max'" v-model.number="item.flowT" @change="save"/><span v-else>AUTO</span></td>
      <td><select v-model="item.mode" @change="save">
        <option>min</option>
        <option>max</option>
      </select></td>
      <td><button class="btn" @click="delete_dhw(index)"><i class="icon-trash"></i></button></td> 
    </tr>
  </table>
  <?php } ?>
</div>


<script>
var config = {};
var app = {};
var save_inst = false;
var feeds = {};

$.ajax({ url: path+"hpctrl/get-config", dataType: 'json', success: function(result){

    if (!result || result==null) {
        config = {
            "heating": [
                {"start":"0000","set_point":5,"flowT":20.0,"mode":"min"}
            ],
            "dhw": [
                {"start":"0200","T":42.0,"flowT":'auto', "mode":"min"},
                {"start":"1400","T":42.0,"flowT":'auto', "mode":"min"}
            ]
        }
    } else {
        config = result
        
        if (config.heating==undefined) config.heating = [];
        if (config.heating.length==0) config.heating[0] = {"start":"0000","set_point":5,"flowT":20.0,"mode":"min"};
    }
    
    app = Vue.createApp({
        data: function() {
            return {
                config:config,
                
                time: '',
                current_set_point: 18.0,
                
                active_period: 0,
                
                room_temperature:'',
                flow_temperature:'',
                outside_temperature:'',
                heatpump_elec:'',
                heatpump_heat:'',
                heatpump_cop:0
            }
        },
        methods: {
            toFixed: function(val,dp) {
                if (!isNaN(val)) {
                    val = val * 1;
                    return val.toFixed(dp)
                } else {
                    return val
                }
            },
            save: function() {
                $.ajax({ method: "POST", url: path+"hpctrl/set-config", data:"config="+JSON.stringify(config), dataType: 'json', async: false, success: function(result){
                    if (result.success!=undefined && result.success) {
                        $(".saved").show();
                        setTimeout(function(){
                            $(".saved").hide();
                        },2000);
                    } else {
                        alert("Could not save")
                    }
                }});
                update_active();
            },
            add_space: function() {
                if (config["heating"].length>0) {
                    var last = JSON.parse(JSON.stringify(config["heating"][config["heating"].length-1]))
                    last.h += 1;
                    if (last.h>23) last.h = 23;
                    config["heating"].push(last);       
                } else {
                    config["heating"].push({"h":0,"set_point":20.0,"flowT":32.0,"mode":"max"});
                }
                app.save();
            },
            add_dhw: function() {
                if (config["dhw"].length>0) {       
                    var last = JSON.parse(JSON.stringify(config["dhw"][config["dhw"].length-1]))
                    config["dhw"].push(last);
                } else {
                    config["dhw"].push({"start":"0700","T":40.0,"flowT":"auto","mode":"min"});
                }
                app.save();
            },
            delete_space: function(index) {
                config["heating"].splice(index,1);  
                app.save();
            },
            delete_dhw: function(index) {
                config["dhw"].splice(index,1);
                app.save();
            },
            inc_set_point: function() {
                app.config.heating[app.active_period].set_point += 0.1;
                app.config.heating[app.active_period].set_point = app.config.heating[app.active_period].set_point.toFixed(1)
                app.config.heating[app.active_period].set_point *= 1;
                clearTimeout(save_inst);
                save_inst = setTimeout(function() {app.save()},2000); 
            },
            dec_set_point: function() {
                app.config.heating[app.active_period].set_point -= 0.1;        
                app.config.heating[app.active_period].set_point = app.config.heating[app.active_period].set_point.toFixed(1)
                app.config.heating[app.active_period].set_point *= 1;
                clearTimeout(save_inst);
                save_inst = setTimeout(function() {app.save()},2000); 
            }
        }
    }).mount('#app');
    update();
}});

function update(){
    
    $.ajax({
        url: path+"feed/list.json",
        dataType: 'json', async: true,
        success: function(data) {
            feeds = data;
            
            feeds_by_name = {}
            for (var z in feeds) {
                feeds_by_name[feeds[z].name] = feeds[z]
            }
            
            if (feeds_by_name['Diningroom_2']!=undefined) {
                app.room_temperature = feeds_by_name['Diningroom_2'].value;
            }
            if (feeds_by_name['heatpump_flowT']!=undefined) {
                app.flow_temperature = feeds_by_name['heatpump_flowT'].value;
            }
            if (feeds_by_name['heatpump_ambient']!=undefined) {
                app.outside_temperature = feeds_by_name['heatpump_ambient'].value;
            }
            if (feeds_by_name['heatpump_elec']!=undefined) {
                app.heatpump_elec = feeds_by_name['heatpump_elec'].value;
            }
            if (feeds_by_name['heatpump_heat']!=undefined) {
                app.heatpump_heat = feeds_by_name['heatpump_heat'].value;
            }
            if (feeds_by_name['heatpump_elec']!=undefined && feeds_by_name['heatpump_heat']!=undefined) {
                app.heatpump_cop = app.heatpump_heat / app.heatpump_elec
            }
        }
    });
    update_active();
}

function update_active() {
    var d = new Date();
    h = d.getHours();
    m = d.getMinutes();
    app.time = String(h).padStart(2,'0')+":"+String(m).padStart(2,'0')
    var hm = String(h).padStart(2,'0')+String(m).padStart(2,'0')
    
    var h = h+(m/60)
    for (var z in app.config.heating) {
        if (parseInt(hm)>=parseInt(app.config.heating[z].start)) {
            app.current_set_point = app.config.heating[z].set_point
            app.active_period = z
        }
    }
}

setInterval(update,10000);

</script>
