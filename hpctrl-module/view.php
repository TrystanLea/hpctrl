<?php
defined('EMONCMS_EXEC') or die('Restricted access');
global $path;

load_js("Lib/js/vue.global.prod-3.5.22.min.js");
load_css("Modules/app/Views/css/app-kit.css");
load_css("Modules/hpctrl/style.css");
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
        <b>{{ ready ? 'Ready' : 'Choose a room temperature feed' }}</b>
        <span>{{ feeds_connected }} of {{ feed_defs.length }} feeds connected</span>
      </div>
      <div class="hp-ready-bar"><div :style="{ width: (100 * feeds_connected / feed_defs.length) + '%' }"></div></div>
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

// Colour scale, fixed in degrees so a colour always means the same temperature
var TICKS = 90;
var COLOR_STOPS = [
    [5,    [61, 120, 216]],
    [12,   [68, 179, 226]],
    [16,   [92, 198, 168]],
    [18.5, [231, 194, 68]],
    [20.5, [245, 163, 92]],
    [23,   [232, 96, 76]],
    [25,   [217, 67, 104]]
];

// Live value feeds. Without a saved choice the first feed found by name is used.
var FEEDS = [
    { key: 'room',    label: 'Room temperature',    unit: '°C', required: true, icon: 'svg-icon-home',
      description: 'Shown on the dial, sets heating or holding', names: ['heatpump_roomT', 'room_temperature', 'roomT'] },
    { key: 'flow',    label: 'Flow temperature',    unit: '°C', icon: 'svg-icon-radiator',
      description: 'Heat pump flow temperature', names: ['heatpump_flowT'] },
    { key: 'outside', label: 'Outside temperature', unit: '°C', icon: 'svg-icon-earth',
      description: 'Outside or heat pump ambient temperature', names: ['heatpump_outsideT', 'heatpump_ambient'] },
    { key: 'elec',    label: 'Electric input',      unit: 'W', icon: 'svg-icon-smartmeter',
      description: 'Heat pump electric power', names: ['heatpump_elec'] },
    { key: 'heat',    label: 'Heat output',         unit: 'W', icon: 'svg-icon-sun',
      description: 'Heat pump heat output, with electric input gives COP', names: ['heatpump_heat'] }
];

var DIAL_DEFAULTS = { dial_min: 5, dial_max: 25, dial_step: 0.1 };

function default_config() {
    return {
        heating: [{ start: "0000", set_point: 5, flowT: 20.0, mode: "min" }],
        dhw: [
            { start: "0200", T: 42.0, flowT: "auto", mode: "min" },
            { start: "1400", T: 42.0, flowT: "auto", mode: "min" }
        ]
    };
}

$.ajax({ url: path + "hpctrl/get-config", dataType: 'json', success: function (result) {
    var schedule = result ? result : default_config();
    if (!schedule.heating || !schedule.heating.length) schedule.heating = default_config().heating;
    if (!schedule.dhw) schedule.dhw = [];
    start_app(schedule);
}});

function start_app(schedule) {
    var save_timer = false;
    var saved_timer = false;
    var step_timer = false;
    var settings_timer = false;

    if (!settings || Array.isArray(settings)) settings = {};
    for (var key in DIAL_DEFAULTS) {
        if (settings[key] === undefined) settings[key] = DIAL_DEFAULTS[key];
    }

    Vue.createApp({
        data: function () {
            return {
                schedule: schedule,
                settings: settings,
                feed_defs: FEEDS,
                feeds: [],
                feeds_loaded: false,
                view: 'control',
                settings_state: '',
                dhw_enable: dhw_enable,
                now: new Date(),
                save_state: '',
                focus_index: -1,
                dragging: false,
                row_els: []
            };
        },
        computed: {
            t_min: function () {
                return this.settings.dial_min * 1;
            },
            t_max: function () {
                return Math.max(this.settings.dial_max * 1, this.t_min + 1);
            },
            feeds_by_id: function () {
                var out = {};
                this.feeds.forEach(function (f) { out[f.id] = f; });
                return out;
            },
            // Feed list grouped by node for the pickers
            feed_groups: function () {
                var groups = {};
                this.feeds.forEach(function (f) {
                    var tag = f.tag || 'No node';
                    if (!groups[tag]) groups[tag] = [];
                    groups[tag].push(f);
                });
                return Object.keys(groups).sort().map(function (tag) {
                    return { tag: tag, feeds: groups[tag].sort(function (a, b) { return a.name.localeCompare(b.name); }) };
                });
            },
            feed_rows: function () {
                var self = this;
                return FEEDS.map(function (def) {
                    var choice = self.settings[def.key];
                    var feed = self.resolve(def);
                    var state = feed ? (choice === undefined ? 'auto' : 'ok') : (choice === 0 || !def.required ? 'off' : 'miss');
                    return { def: def, feed: feed, state: state, choice: choice === undefined ? 'auto' : String(choice) };
                });
            },
            feeds_connected: function () {
                return this.feed_rows.filter(function (r) { return r.feed; }).length;
            },
            // Live values, false when no feed or no value
            room: function () { return this.live_value('room'); },
            flow: function () { return this.live_value('flow'); },
            outside: function () { return this.live_value('outside'); },
            elec: function () { return this.live_value('elec'); },
            heat: function () { return this.live_value('heat'); },
            live: function () {
                return !this.feed_stale(this.resolve(FEEDS[0]));
            },
            ready: function () {
                return !this.feed_rows.some(function (r) { return r.state == 'miss'; });
            },
            now_minutes: function () {
                return this.now.getHours() * 60 + this.now.getMinutes();
            },
            // Last period started today, else the last period from yesterday, as hpctrl.py
            active_index: function () {
                var list = this.schedule.heating;
                var index = list.length - 1;
                for (var i = 0; i < list.length; i++) {
                    if (this.now_minutes >= this.minutes(list[i].start)) index = i;
                }
                return index;
            },
            active: function () {
                return this.schedule.heating[this.active_index];
            },
            set_point: function () {
                return this.active.set_point * 1;
            },
            sp_angle: function () {
                return this.angle(this.set_point);
            },
            sp_color: function () {
                return this.temp_color(this.set_point);
            },
            room_angle: function () {
                return this.room === false ? false : this.angle(this.room);
            },
            // Same 0.1 hysteresis as hpctrl.py
            heating: function () {
                return this.room !== false && this.room <= this.set_point - 0.1;
            },
            state_text: function () {
                if (this.room === false) return 'Set point';
                if (this.heating) return 'Heating';
                if (this.room >= this.set_point + 0.1) return 'Above set point';
                return 'Holding';
            },
            ticks: function () {
                var out = [];
                for (var i = 0; i < TICKS; i++) {
                    var t = this.t_min + (this.t_max - this.t_min) * i / (TICKS - 1);
                    var lit = t <= this.set_point + 0.01;
                    var warming = this.heating && lit && t > this.room;
                    var p1 = this.polar(this.angle(t), lit ? 114 : 118);
                    var p2 = this.polar(this.angle(t), lit ? 134 : 130);
                    out.push({
                        i: i, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y,
                        cls: 'hp-tick' + (lit ? ' is-lit' : '') + (warming ? ' is-warming' : ''),
                        style: {
                            stroke: lit ? this.temp_color(t) : null,
                            animationDelay: warming ? (i * 0.04) + 's' : null
                        }
                    });
                }
                return out;
            },
            next_text: function () {
                var list = this.schedule.heating;
                if (list.length < 2) return 'all day';
                var next = list[(this.active_index + 1) % list.length];
                return this.fmt_time(next.start) + ', then ' + (next.set_point * 1).toFixed(1) + '°';
            },
            // Day profile. Time before the first start belongs to the last period.
            segments: function () {
                var self = this;
                var list = this.schedule.heating;
                var segs = [];
                var add = function (index, from, to) {
                    if (to <= from) return;
                    var sp = list[index].set_point * 1;
                    segs.push({
                        index: index, start: list[index].start, set_point: sp,
                        left: from / 14.4, width: (to - from) / 14.4,
                        height: 18 + 82 * self.clamp((sp - self.t_min) / (self.t_max - self.t_min), 0, 1),
                        color: self.temp_color(sp)
                    });
                };
                add(list.length - 1, 0, this.minutes(list[0].start));
                for (var i = 0; i < list.length; i++) {
                    var end = i + 1 < list.length ? this.minutes(list[i + 1].start) : 1440;
                    add(i, this.minutes(list[i].start), end);
                }
                return segs;
            },
            now_pct: function () {
                return this.now_minutes / 14.4;
            },
            cop: function () {
                if (this.elec === false || this.heat === false || this.elec < 50) return '-';
                return (this.heat / this.elec).toFixed(1);
            },
            clock: function () {
                return this.pad(this.now.getHours()) + ':' + this.pad(this.now.getMinutes());
            },
            save_text: function () {
                return this.state_label(this.save_state);
            }
        },
        methods: {
            state_label: function (state) {
                return { saving: 'Saving', saved: 'Saved', error: 'Not saved' }[state];
            },
            pad: function (n) {
                return String(n).padStart(2, '0');
            },
            clamp: function (v, lo, hi) {
                return Math.min(hi, Math.max(lo, v));
            },
            fixed: function (val, dp) {
                return val === false ? '--' : val.toFixed(dp);
            },
            // Start times are stored as HHMM strings
            minutes: function (start) {
                var s = String(start).padStart(4, '0');
                return parseInt(s.substr(0, 2)) * 60 + parseInt(s.substr(2, 2));
            },
            fmt_time: function (start) {
                var s = String(start).padStart(4, '0');
                return s.substr(0, 2) + ':' + s.substr(2, 2);
            },
            angle: function (t) {
                return 135 + 270 * this.clamp((t - this.t_min) / (this.t_max - this.t_min), 0, 1);
            },
            polar: function (deg, r) {
                var a = deg * Math.PI / 180;
                return { x: 150 + r * Math.cos(a), y: 150 + r * Math.sin(a) };
            },
            temp_color: function (t) {
                t = this.clamp(t * 1 || 0, COLOR_STOPS[0][0], COLOR_STOPS[COLOR_STOPS.length - 1][0]);
                for (var i = 1; i < COLOR_STOPS.length; i++) {
                    if (t <= COLOR_STOPS[i][0]) {
                        var a = COLOR_STOPS[i - 1], b = COLOR_STOPS[i];
                        var f = (t - a[0]) / (b[0] - a[0]);
                        var c = a[1].map(function (v, k) { return Math.round(v + (b[1][k] - v) * f); });
                        return 'rgb(' + c.join(',') + ')';
                    }
                }
            },

            // Set point
            set_set_point: function (t) {
                t = Math.round(this.clamp(t, this.t_min, this.t_max) * 10) / 10;
                if (t === this.active.set_point) return;
                this.active.set_point = t;
                this.save_later();
            },
            nudge: function (d) {
                this.set_set_point(this.set_point + d);
            },
            // Hold to repeat
            step_start: function (d) {
                var self = this;
                this.nudge(d);
                clearTimeout(step_timer);
                step_timer = setTimeout(function repeat() {
                    self.nudge(d);
                    step_timer = setTimeout(repeat, 90);
                }, 450);
            },
            step_end: function () {
                clearTimeout(step_timer);
            },
            pointer_temp: function (e) {
                var box = this.$refs.dial.getBoundingClientRect();
                var x = (e.clientX - box.left) / box.width * 300 - 150;
                var y = (e.clientY - box.top) / box.height * 300 - 150;
                var rel = Math.atan2(y, x) * 180 / Math.PI - 135;
                while (rel < 0) rel += 360;
                if (rel > 270) rel = rel > 315 ? 0 : 270;
                return { t: this.t_min + (this.t_max - this.t_min) * rel / 270, r: Math.sqrt(x * x + y * y) };
            },
            drag_start: function (e) {
                var p = this.pointer_temp(e);
                if (p.r < 92 || p.r > 155) return;
                this.dragging = true;
                this.$refs.dial.setPointerCapture(e.pointerId);
                this.set_set_point(p.t);
            },
            drag_move: function (e) {
                if (this.dragging) this.set_set_point(this.pointer_temp(e).t);
            },
            drag_end: function () {
                this.dragging = false;
            },

            // Schedule
            open_picker: function (e) {
                try { e.target.showPicker(); } catch (err) {}
            },
            set_start: function (item, e) {
                if (!e.target.value) return;
                item.start = e.target.value.replace(':', '');
                this.save();
            },
            set_mode: function (item, mode) {
                item.mode = mode;
                this.save();
            },
            set_dhw_mode: function (item, mode) {
                item.mode = mode;
                if (mode == 'max' && isNaN(parseFloat(item.flowT))) item.flowT = 50;
                this.save();
            },
            add_heating: function () {
                var list = this.schedule.heating;
                var last = JSON.parse(JSON.stringify(list[list.length - 1]));
                var m = Math.min(this.minutes(last.start) + 60, 23 * 60 + 59);
                last.start = this.pad(Math.floor(m / 60)) + this.pad(m % 60);
                list.push(last);
                this.save();
                this.focus_row(list.length - 1);
            },
            delete_heating: function (index) {
                if (this.schedule.heating.length < 2) return;
                this.schedule.heating.splice(index, 1);
                this.save();
            },
            add_dhw: function () {
                var list = this.schedule.dhw;
                if (list.length) list.push(JSON.parse(JSON.stringify(list[list.length - 1])));
                else list.push({ start: "0700", T: 40.0, flowT: "auto", mode: "min" });
                this.save();
            },
            delete_dhw: function (index) {
                this.schedule.dhw.splice(index, 1);
                this.save();
            },
            focus_row: function (index) {
                var self = this;
                this.focus_index = index;
                this.$nextTick(function () {
                    var el = self.row_els[index];
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                });
                setTimeout(function () { if (self.focus_index == index) self.focus_index = -1; }, 1600);
            },

            // Saving. Lists are kept in start order, as hpctrl.py takes the last match.
            sort: function () {
                var self = this;
                var by_start = function (a, b) { return self.minutes(a.start) - self.minutes(b.start); };
                this.schedule.heating.sort(by_start);
                this.schedule.dhw.sort(by_start);
            },
            save_later: function () {
                var self = this;
                clearTimeout(save_timer);
                save_timer = setTimeout(function () { self.save(); }, 1500);
            },
            save: function () {
                var self = this;
                clearTimeout(save_timer);
                this.sort();
                this.save_state = 'saving';
                $.ajax({
                    method: "POST", url: path + "hpctrl/set-config", dataType: 'json',
                    data: { config: JSON.stringify(this.schedule) },
                    success: function (result) {
                        self.save_state = (result && result.success) ? 'saved' : 'error';
                    },
                    error: function () {
                        self.save_state = 'error';
                    },
                    complete: function () {
                        clearTimeout(saved_timer);
                        if (self.save_state == 'saved') {
                            saved_timer = setTimeout(function () { self.save_state = ''; }, 2500);
                        }
                    }
                });
            },

            // Settings
            resolve: function (def) {
                var choice = this.settings[def.key];
                if (choice === 0) return false;
                if (choice !== undefined) return this.feeds_by_id[choice] || false;
                for (var i = 0; i < def.names.length; i++) {
                    var match = this.feeds.find(function (f) { return f.name == def.names[i]; });
                    if (match) return match;
                }
                return false;
            },
            live_value: function (key) {
                var f = this.resolve(FEEDS.find(function (d) { return d.key == key; }));
                return (f && f.value !== null && !isNaN(f.value)) ? f.value * 1 : false;
            },
            set_feed: function (key, value) {
                if (value == 'auto') delete this.settings[key];
                else this.settings[key] = value * 1;
                this.save_settings();
            },
            set_dial: function (key, value) {
                value = parseFloat(value);
                if (isNaN(value)) return;
                this.settings[key] = value;
                this.save_settings();
            },
            feed_value: function (feed, unit) {
                if (!feed || feed.value === null || isNaN(feed.value)) return '--';
                return (feed.value * 1).toFixed(unit == 'W' ? 0 : 1) + (unit == 'W' ? ' W' : '°C');
            },
            feed_age: function (feed) {
                if (!feed || !feed.time) return '';
                var s = Math.max(0, Math.round(this.now.getTime() / 1000 - feed.time));
                if (s < 60) return s + 's ago';
                if (s < 3600) return Math.round(s / 60) + ' min ago';
                if (s < 86400) return Math.round(s / 3600) + ' h ago';
                return Math.round(s / 86400) + ' days ago';
            },
            feed_stale: function (feed) {
                return !feed || this.now.getTime() / 1000 - feed.time > 300;
            },
            save_settings: function () {
                var self = this;
                this.settings_state = 'saving';
                $.ajax({
                    method: "POST", url: path + "hpctrl/set-settings", dataType: 'json',
                    data: { settings: JSON.stringify(this.settings) },
                    success: function (result) {
                        self.settings_state = (result && result.success) ? 'saved' : 'error';
                    },
                    error: function () {
                        self.settings_state = 'error';
                    },
                    complete: function () {
                        clearTimeout(settings_timer);
                        if (self.settings_state == 'saved') {
                            settings_timer = setTimeout(function () { self.settings_state = ''; }, 2500);
                        }
                    }
                });
            },
            open_settings: function () {
                this.view = 'settings';
                window.scrollTo(0, 0);
            },
            close_settings: function () {
                if (!this.ready) return;
                this.view = 'control';
                window.scrollTo(0, 0);
            },

            // Live values
            update: function () {
                var self = this;
                this.now = new Date();
                $.ajax({ url: path + "feed/list.json", dataType: 'json', cache: false, success: function (feeds) {
                    if (!Array.isArray(feeds)) return;
                    self.feeds = feeds;
                    // First visit without a room feed: open settings
                    if (!self.feeds_loaded && !self.ready) self.view = 'settings';
                    self.feeds_loaded = true;
                }});
            }
        },
        mounted: function () {
            var self = this;
            this.update();
            setInterval(function () { self.update(); }, 10000);
        }
    }).mount('#hpctrl');
}
</script>
