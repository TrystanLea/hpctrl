<?php
defined('EMONCMS_EXEC') or die('Restricted access');
global $path;

load_js("Lib/js/vue.global.prod-3.5.22.min.js");
load_css("Modules/app/Views/css/app-kit.css");
load_css("Modules/hpctrl/Views/hpctrl.css");
?>

<div class="app-page hp-page" data-bs-theme="dark">
<section id="app-block" class="block">
<div id="hpctrl" v-cloak>
<div class="hp-grid" v-if="view=='control'">

  <!-- Thermostat -->
  <div class="app-card hp-thermostat">
    <nav class="app-card-head">
      <div class="nav nav-underline">
        <span class="nav-link active"><i class="svg-icon-radiator"></i>Heat pump</span>
      </div>
      <div class="app-card-tools">
        <span class="hp-save" :class="'is-'+save_state" v-if="save_state">{{ save_text }}</span>
        <span class="app-status" :class="{ 'is-live': live }"><span class="app-status-dot"></span><span class="app-status-text">{{ clock }}</span></span>
        <div class="nav">
          <button class="nav-link" title="Settings" @click="open_settings"><i class="svg-icon-wrench"></i></button>
        </div>
      </div>
    </nav>

    <div class="hp-dial-wrap" :class="{ 'is-heating': heating }" :style="{ '--hp-sp-color': sp_color }">
      <div class="hp-dial-glow"></div>
      <svg class="hp-dial" viewBox="0 0 300 300" ref="dial"
           @pointerdown="drag_start" @pointermove="drag_move" @pointerup="drag_end" @pointercancel="drag_end">
        <line v-for="tick in ticks" :key="tick.i"
              :x1="tick.x1" :y1="tick.y1" :x2="tick.x2" :y2="tick.y2"
              :class="tick.cls" :style="tick.style"/>
        <circle v-if="room_angle!==false" class="hp-room-dot"
                :cx="polar(room_angle,100).x" :cy="polar(room_angle,100).y" r="3.5"/>
        <circle class="hp-handle" :cx="polar(sp_angle,124).x" :cy="polar(sp_angle,124).y" r="11"/>
      </svg>

      <div class="hp-dial-face">
        <div class="hp-dial-state">{{ state_text }}</div>
        <div class="hp-dial-sp">{{ set_point.toFixed(1) }}<span class="hp-deg">&deg;</span></div>
        <div class="hp-dial-room">Room <b>{{ room===false ? '--' : room.toFixed(1)+'°' }}</b></div>
      </div>

      <button class="hp-step hp-step-down" title="Lower set point"
              @pointerdown.prevent="step_start(-settings.dial_step)" @pointerup="step_end" @pointerleave="step_end" @keydown.enter.prevent="nudge(-settings.dial_step)">&minus;</button>
      <button class="hp-step hp-step-up" title="Raise set point"
              @pointerdown.prevent="step_start(settings.dial_step)" @pointerup="step_end" @pointerleave="step_end" @keydown.enter.prevent="nudge(settings.dial_step)">+</button>
    </div>

    <div class="hp-period-note">
      <span class="hp-chip" :style="{ '--chip': sp_color }">{{ fmt_time(active.start) }}</span>
      <span>until {{ next_text }}</span>
      <span class="hp-dot-sep"></span>
      <span>Flow {{ active.mode }} {{ active.flowT }}&deg;</span>
    </div>

    <div class="app-live hp-live">
      <div>
        <div class="app-live-label">Flow</div>
        <div class="app-live-value hp-text-flow">{{ fixed(flow,1) }}<span class="power-unit">&deg;C</span></div>
      </div>
      <div>
        <div class="app-live-label">Outside</div>
        <div class="app-live-value hp-text-outside">{{ fixed(outside,1) }}<span class="power-unit">&deg;C</span></div>
      </div>
      <div>
        <div class="app-live-label">Elec</div>
        <div class="app-live-value text-use">{{ fixed(elec,0) }}<span class="power-unit">W</span></div>
      </div>
      <div>
        <div class="app-live-label">Heat</div>
        <div class="app-live-value hp-text-heat">{{ fixed(heat,0) }}<span class="power-unit">W</span></div>
      </div>
      <div>
        <div class="app-live-label">COP</div>
        <div class="app-live-value">{{ cop }}</div>
      </div>
    </div>

    <!-- Day profile -->
    <div class="hp-profile">
      <div class="hp-profile-plot">
        <div v-for="seg in segments" class="hp-seg"
             :class="{ 'is-active': seg.index==active_index }"
             :style="{ left: seg.left+'%', width: seg.width+'%', height: seg.height+'%', '--seg': seg.color }"
             :title="fmt_time(seg.start)+'  '+seg.set_point+'°'"
             @click="focus_row(seg.index)">
          <span v-if="seg.width>7">{{ seg.set_point }}&deg;</span>
        </div>
        <div class="hp-now" :style="{ left: now_pct+'%' }"></div>
        <template v-if="dhw_enable">
          <div v-for="run in schedule.dhw" class="hp-dhw-pin"
               :style="{ left: minutes(run.start)/14.4+'%' }" :title="'Hot water '+fmt_time(run.start)+'  '+run.T+'°'">
            <i class="svg-icon-shower"></i>
          </div>
        </template>
      </div>
      <div class="hp-profile-axis"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div>
    </div>
  </div>

  <div class="hp-side">

    <!-- Space heating -->
    <div class="app-card">
      <div class="app-card-head">
        <div class="nav nav-underline">
          <span class="nav-link active"><i class="svg-icon-schedule"></i>Space heating</span>
        </div>
        <div class="app-card-tools nav">
          <button class="nav-link" title="Add period" @click="add_heating"><i class="svg-icon-plus"></i>Add</button>
        </div>
      </div>
      <div class="app-card-body">
        <div class="hp-rows">
          <div class="hp-rows-head"><span>Start</span><span>Set &deg;C</span><span>Flow &deg;C</span><span>Mode</span></div>
          <div v-for="(item,index) in schedule.heating" :key="index" class="hp-row"
               :class="{ 'is-active': index==active_index, 'is-focus': index==focus_index }"
               :style="{ '--row': temp_color(item.set_point) }" :ref="el => { if (el) row_els[index] = el }">
            <input type="time" class="form-control form-control-sm" title="Start" @click="open_picker" :value="fmt_time(item.start)" @change="set_start(item,$event)"/>
            <input type="number" step="0.1" class="form-control form-control-sm" title="Set point" v-model.number="item.set_point" @change="save"/>
            <input type="number" step="0.5" class="form-control form-control-sm" title="Flow temperature" v-model.number="item.flowT" @change="save"/>
            <div class="btn-group btn-group-sm app-segmented">
              <button class="btn" :class="{ active: item.mode=='min' }" @click="set_mode(item,'min')" title="Flow temperature follows return temperature, capped at flow">Min</button>
              <button class="btn" :class="{ active: item.mode=='max' }" @click="set_mode(item,'max')" title="Fixed flow temperature">Max</button>
            </div>
            <button class="hp-row-delete nav-link" title="Delete period" @click="delete_heating(index)" :disabled="schedule.heating.length<2"><i class="svg-icon-trash"></i></button>
          </div>
        </div>

      </div>
    </div>

    <!-- Hot water -->
    <div class="app-card" v-if="dhw_enable">
      <div class="app-card-head">
        <div class="nav nav-underline">
          <span class="nav-link active"><i class="svg-icon-shower"></i>Hot water</span>
        </div>
        <div class="app-card-tools nav">
          <button class="nav-link" title="Add run" @click="add_dhw"><i class="svg-icon-plus"></i>Add</button>
        </div>
      </div>
      <div class="app-card-body">
        <div class="hp-rows">
          <div class="hp-rows-head" v-if="schedule.dhw.length"><span>Start</span><span>Target &deg;C</span><span>Flow &deg;C</span><span>Mode</span></div>
          <div v-for="(item,index) in schedule.dhw" :key="index" class="hp-row hp-row-dhw">
            <input type="time" class="form-control form-control-sm" title="Start" @click="open_picker" :value="fmt_time(item.start)" @change="set_start(item,$event)"/>
            <input type="number" step="0.5" class="form-control form-control-sm" title="Target" v-model.number="item.T" @change="save"/>
            <input v-if="item.mode=='max'" type="number" step="0.5" class="form-control form-control-sm" title="Flow temperature" v-model.number="item.flowT" @change="save"/>
            <div class="hp-auto" v-else>Auto</div>
            <div class="btn-group btn-group-sm app-segmented">
              <button class="btn" :class="{ active: item.mode=='min' }" @click="set_dhw_mode(item,'min')">Min</button>
              <button class="btn" :class="{ active: item.mode=='max' }" @click="set_dhw_mode(item,'max')">Max</button>
            </div>
            <button class="hp-row-delete nav-link" title="Delete run" @click="delete_dhw(index)"><i class="svg-icon-trash"></i></button>
          </div>
          <div v-if="!schedule.dhw.length" class="hp-empty">No hot water runs</div>
        </div>
      </div>
    </div>

    <!-- Activity: status and events from the hpctrl service -->
    <div class="app-card">
      <div class="app-card-head">
        <div class="nav nav-underline">
          <span class="nav-link active"><i class="svg-icon-list"></i>Activity</span>
        </div>
        <div class="app-card-tools">
          <span class="hp-badge is-auto" v-if="status_live && status.dry_run">Dry run</span>
          <span class="app-status" :class="{ 'is-live': status_live && !status.dry_run }"><span class="app-status-dot"></span><span class="app-status-text">{{ service_text }}</span></span>
        </div>
      </div>
      <div class="app-card-body">
        <div class="hp-now-status" v-if="status_live">
          <div class="hp-now-reason"><b>{{ status.label }}</b>{{ status.reason }}</div>
          <div class="hp-now-stats" v-if="status.outputs">
            <span>Pump <b>{{ status.outputs.power ? 'on' : 'off' }}</b></span>
            <span>Flow target <b>{{ status.outputs.flowT }}&deg;</b></span>
            <span>Valve <b>{{ status.outputs.valve ? 'hot water' : 'heating' }}</b></span>
            <span v-if="status.ecodan && status.ecodan.freq !== undefined">Compressor <b>{{ status.ecodan.freq }} Hz</b></span>
          </div>
          <button v-if="waiting_for_inputs" class="btn btn-sm btn-primary hp-now-action" @click="open_settings"><i class="svg-icon-input"></i> Choose inputs</button>
        </div>
        <div class="hp-now-status is-offline" v-else>
          {{ status ? 'No update from the hpctrl service for ' + ago(status_age) : 'The hpctrl service has not reported yet' }}
        </div>

        <div class="hp-events" v-if="events.length">
          <div v-for="(e, index) in events_shown" :key="index" class="hp-event" :class="'is-' + e.type">
            <span class="hp-event-time">{{ event_time(e.time) }}</span>
            <span class="hp-event-text">{{ e.text }}</span>
          </div>
          <button v-if="events.length > 8" class="nav-link hp-events-more" @click="show_all_events = !show_all_events">
            {{ show_all_events ? 'Show fewer' : 'Show ' + (events.length - 8) + ' more' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- Settings -->
<div class="hp-settings" v-else>
  <div class="app-card">
    <nav class="app-card-head">
      <div class="nav nav-underline">
        <span class="nav-link active"><i class="svg-icon-wrench"></i>Settings</span>
      </div>
      <div class="app-card-tools">
        <span class="hp-save" :class="'is-'+settings_state" v-if="settings_state">{{ state_label(settings_state) }}</span>
        <div class="nav">
          <button class="nav-link" title="Close" @click="close_settings" :disabled="!ready"><i class="svg-icon-close"></i></button>
        </div>
      </div>
    </nav>

    <div class="hp-ready" :class="ready ? 'is-ready' : 'is-missing'">
      <span class="hp-state-icon"><i :class="ready ? 'svg-icon-check' : 'svg-icon-close'"></i></span>
      <div class="hp-ready-text">
        <b>{{ ready ? 'Ready' : 'Choose the required feeds and inputs' }}</b>
        <span>{{ ready_count }} of {{ ready_total }} connected</span>
      </div>
      <div class="hp-ready-bar"><div :style="{ width: (100 * ready_count / ready_total) + '%' }"></div></div>
    </div>
  </div>

  <div class="app-section-label hp-settings-label">Feeds</div>
  <div class="app-card">
    <div v-for="row in feed_rows" :key="row.def.key" class="hp-feed" :class="'is-' + row.state">
      <span class="hp-state-icon"><i :class="row.def.icon"></i></span>
      <div class="hp-feed-text">
        <div class="hp-feed-name">{{ row.def.label }}
          <span v-if="row.state=='miss'" class="hp-badge is-miss">Required</span>
          <span v-else-if="row.state=='auto'" class="hp-badge is-auto">Auto</span>
        </div>
        <div class="hp-feed-desc">{{ row.def.description }}</div>
      </div>
      <div class="hp-feed-pick">
        <select class="form-select form-select-sm" :value="row.choice" @change="set_feed(row.def.key, $event.target.value)">
          <option value="auto">Auto ({{ row.def.names.join(', ') }})</option>
          <option value="0" v-if="!row.def.required">Not used</option>
          <optgroup v-for="group in feed_groups" :label="group.tag">
            <option v-for="f in group.feeds" :value="String(f.id)">{{ f.name }}</option>
          </optgroup>
        </select>
        <div class="hp-feed-live" v-if="row.feed">
          <span class="hp-feed-node">{{ row.feed.tag }}:{{ row.feed.name }}</span>
          <b>{{ feed_value(row.feed, row.def.unit) }}</b>
          <span :class="{ 'is-stale': feed_stale(row.feed) }">{{ feed_age(row.feed) }}</span>
        </div>
        <div class="hp-feed-live" v-else-if="row.state=='miss'">No feed found by name</div>
        <div class="hp-feed-live" v-else>Not shown</div>
      </div>
    </div>
  </div>

  <div class="app-section-label hp-settings-label">Control inputs</div>
  <div class="hp-settings-note">Read by the hpctrl service from emoncms inputs. Shared by all users.</div>
  <div class="app-card">
    <div v-if="!inputs_loaded" class="hp-feed"><span class="hp-feed-desc">Loading inputs&hellip;</span></div>
    <div v-else v-for="row in input_rows" :key="row.def.key" class="hp-feed" :class="'is-' + row.state">
      <span class="hp-state-icon"><i :class="row.def.icon"></i></span>
      <div class="hp-feed-text">
        <div class="hp-feed-name">{{ row.def.label }}
          <span v-if="row.state=='miss'" class="hp-badge is-miss">Required</span>
          <span v-else-if="row.state=='stale'" class="hp-badge is-stale">Stale</span>
        </div>
        <div class="hp-feed-desc">{{ row.def.description }}</div>
      </div>
      <div class="hp-feed-pick">
        <select class="form-select form-select-sm" :value="row.choice" @change="set_input(row.def.key, $event.target.value)">
          <option value="" disabled>Choose input&hellip;</option>
          <option value="0" v-if="!row.def.required">Not used</option>
          <option v-if="row.state=='miss' && row.choice" :value="row.choice" disabled>Input {{ row.choice }} (not found)</option>
          <optgroup v-for="group in input_groups" :label="group.node">
            <option v-for="i in group.inputs" :value="String(i.id)">{{ i.name }}</option>
          </optgroup>
        </select>
        <div class="hp-feed-live" v-if="row.input">
          <span class="hp-feed-node">{{ row.input.nodeid }}:{{ row.input.name }}</span>
          <b>{{ input_value(row.input, row.def) }}</b>
          <span :class="{ 'is-stale': row.state=='stale' }">{{ ago(now.getTime() / 1000 - row.input.time) }} ago</span>
        </div>
        <div class="hp-feed-live" v-else-if="row.state=='miss'">{{ row.choice ? 'Input ' + row.choice + ' not found' : 'Not set' }}</div>
        <div class="hp-feed-live" v-else>Not used</div>
      </div>
    </div>
  </div>

  <div class="app-section-label hp-settings-label">Dial</div>
  <div class="app-card hp-dial-settings">
    <div class="hp-setting">
      <div class="hp-feed-text">
        <div class="hp-feed-name">Range</div>
        <div class="hp-feed-desc">Lowest and highest set point on the dial</div>
      </div>
      <div class="hp-range">
        <div class="input-group input-group-sm">
          <input type="number" step="1" class="form-control" :value="settings.dial_min" @change="set_dial('dial_min', $event.target.value)"/>
          <span class="input-group-text">to</span>
          <input type="number" step="1" class="form-control" :value="settings.dial_max" @change="set_dial('dial_max', $event.target.value)"/>
          <span class="input-group-text">&deg;C</span>
        </div>
        <div class="hp-range-bar" :style="{ background: 'linear-gradient(to right, ' + temp_color(t_min) + ', ' + temp_color((t_min + t_max) / 2) + ', ' + temp_color(t_max) + ')' }"></div>
      </div>
    </div>
    <div class="hp-setting">
      <div class="hp-feed-text">
        <div class="hp-feed-name">Step</div>
        <div class="hp-feed-desc">Change per press of &minus; or +</div>
      </div>
      <div class="btn-group btn-group-sm app-segmented">
        <button v-for="step in [0.1, 0.5, 1]" class="btn" :class="{ active: settings.dial_step == step }" @click="set_dial('dial_step', step)">{{ step }}&deg;</button>
      </div>
    </div>
  </div>

  <div class="hp-settings-foot">
    <button class="btn btn-primary" :disabled="!ready" @click="close_settings"><i class="svg-icon-check"></i> Done</button>
  </div>
</div>

</div>
</section>
</div>

<script>
var dhw_enable = <?php echo (isset($dhw_enable) && $dhw_enable) ? 'true' : 'false'; ?>;

var settings = <?php echo json_encode($settings); ?>;
</script>
<?php load_js("Modules/hpctrl/Views/hpctrl.js"); ?>
