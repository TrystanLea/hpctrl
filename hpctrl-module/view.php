<?php
defined('EMONCMS_EXEC') or die('Restricted access');
global $path;

load_js("Lib/js/vue.global.prod-3.5.22.min.js");
load_css("Modules/app/Views/css/app-kit.css");
load_css("Modules/hpctrl/style.css");
?>

<div class="app-page hp-page" data-bs-theme="dark">
<section id="app-block" class="block">
<div id="hpctrl" class="hp-grid" v-cloak>

  <!-- Thermostat -->
  <div class="app-card hp-thermostat">
    <nav class="app-card-head">
      <div class="nav nav-underline">
        <span class="nav-link active"><i class="svg-icon-radiator"></i>Heat pump</span>
      </div>
      <div class="app-card-tools">
        <span class="hp-save" :class="'is-'+save_state" v-if="save_state">{{ save_text }}</span>
        <span class="app-status" :class="{ 'is-live': live }"><span class="app-status-dot"></span><span class="app-status-text">{{ clock }}</span></span>
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
              @pointerdown.prevent="step_start(-0.1)" @pointerup="step_end" @pointerleave="step_end" @keydown.enter.prevent="nudge(-0.1)">&minus;</button>
      <button class="hp-step hp-step-up" title="Raise set point"
              @pointerdown.prevent="step_start(0.1)" @pointerup="step_end" @pointerleave="step_end" @keydown.enter.prevent="nudge(0.1)">+</button>
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
          <div v-for="run in config.dhw" class="hp-dhw-pin"
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
          <div v-for="(item,index) in config.heating" :key="index" class="hp-row"
               :class="{ 'is-active': index==active_index, 'is-focus': index==focus_index }"
               :style="{ '--row': temp_color(item.set_point) }" :ref="el => { if (el) row_els[index] = el }">
            <input type="time" class="form-control form-control-sm" title="Start" @click="open_picker" :value="fmt_time(item.start)" @change="set_start(item,$event)"/>
            <input type="number" step="0.1" class="form-control form-control-sm" title="Set point" v-model.number="item.set_point" @change="save"/>
            <input type="number" step="0.5" class="form-control form-control-sm" title="Flow temperature" v-model.number="item.flowT" @change="save"/>
            <div class="btn-group btn-group-sm app-segmented">
              <button class="btn" :class="{ active: item.mode=='min' }" @click="set_mode(item,'min')" title="Flow temperature follows return temperature, capped at flow">Min</button>
              <button class="btn" :class="{ active: item.mode=='max' }" @click="set_mode(item,'max')" title="Fixed flow temperature">Max</button>
            </div>
            <button class="hp-row-delete nav-link" title="Delete period" @click="delete_heating(index)" :disabled="config.heating.length<2"><i class="svg-icon-trash"></i></button>
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
          <div class="hp-rows-head" v-if="config.dhw.length"><span>Start</span><span>Target &deg;C</span><span>Flow &deg;C</span><span>Mode</span></div>
          <div v-for="(item,index) in config.dhw" :key="index" class="hp-row hp-row-dhw">
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
          <div v-if="!config.dhw.length" class="hp-empty">No hot water runs</div>
        </div>
      </div>
    </div>

  </div>
</div>
</section>
</div>

<script>
var dhw_enable = <?php echo (isset($dhw_enable) && $dhw_enable) ? 'true' : 'false'; ?>;

// Dial range and colour scale
var T_MIN = 5;
var T_MAX = 25;
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

// Feed names for live values
var FEEDS = {
    room: 'Diningroom_2',
    flow: 'heatpump_flowT',
    outside: 'heatpump_ambient',
    elec: 'heatpump_elec',
    heat: 'heatpump_heat'
};

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
    var config = result ? result : default_config();
    if (!config.heating || !config.heating.length) config.heating = default_config().heating;
    if (!config.dhw) config.dhw = [];
    start_app(config);
}});

function start_app(config) {
    var save_timer = false;
    var saved_timer = false;
    var step_timer = false;

    Vue.createApp({
        data: function () {
            return {
                config: config,
                dhw_enable: dhw_enable,
                now: new Date(),
                room: false,
                flow: false,
                outside: false,
                elec: false,
                heat: false,
                live: false,
                save_state: '',
                focus_index: -1,
                dragging: false,
                row_els: []
            };
        },
        computed: {
            now_minutes: function () {
                return this.now.getHours() * 60 + this.now.getMinutes();
            },
            // Last period started today, else the last period from yesterday, as hpctrl.py
            active_index: function () {
                var list = this.config.heating;
                var index = list.length - 1;
                for (var i = 0; i < list.length; i++) {
                    if (this.now_minutes >= this.minutes(list[i].start)) index = i;
                }
                return index;
            },
            active: function () {
                return this.config.heating[this.active_index];
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
                    var t = T_MIN + (T_MAX - T_MIN) * i / (TICKS - 1);
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
                var list = this.config.heating;
                if (list.length < 2) return 'all day';
                var next = list[(this.active_index + 1) % list.length];
                return this.fmt_time(next.start) + ', then ' + (next.set_point * 1).toFixed(1) + '°';
            },
            // Day profile. Time before the first start belongs to the last period.
            segments: function () {
                var self = this;
                var list = this.config.heating;
                var segs = [];
                var add = function (index, from, to) {
                    if (to <= from) return;
                    var sp = list[index].set_point * 1;
                    segs.push({
                        index: index, start: list[index].start, set_point: sp,
                        left: from / 14.4, width: (to - from) / 14.4,
                        height: 18 + 82 * self.clamp((sp - T_MIN) / (T_MAX - T_MIN), 0, 1),
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
                return { saving: 'Saving', saved: 'Saved', error: 'Not saved' }[this.save_state];
            }
        },
        methods: {
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
                return 135 + 270 * this.clamp((t - T_MIN) / (T_MAX - T_MIN), 0, 1);
            },
            polar: function (deg, r) {
                var a = deg * Math.PI / 180;
                return { x: 150 + r * Math.cos(a), y: 150 + r * Math.sin(a) };
            },
            temp_color: function (t) {
                t = this.clamp(t * 1 || 0, T_MIN, T_MAX);
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
                t = Math.round(this.clamp(t, T_MIN, T_MAX) * 10) / 10;
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
                return { t: T_MIN + (T_MAX - T_MIN) * rel / 270, r: Math.sqrt(x * x + y * y) };
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
                var list = this.config.heating;
                var last = JSON.parse(JSON.stringify(list[list.length - 1]));
                var m = Math.min(this.minutes(last.start) + 60, 23 * 60 + 59);
                last.start = this.pad(Math.floor(m / 60)) + this.pad(m % 60);
                list.push(last);
                this.save();
                this.focus_row(list.length - 1);
            },
            delete_heating: function (index) {
                if (this.config.heating.length < 2) return;
                this.config.heating.splice(index, 1);
                this.save();
            },
            add_dhw: function () {
                var list = this.config.dhw;
                if (list.length) list.push(JSON.parse(JSON.stringify(list[list.length - 1])));
                else list.push({ start: "0700", T: 40.0, flowT: "auto", mode: "min" });
                this.save();
            },
            delete_dhw: function (index) {
                this.config.dhw.splice(index, 1);
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
                this.config.heating.sort(by_start);
                this.config.dhw.sort(by_start);
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
                    data: { config: JSON.stringify(this.config) },
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

            // Live values
            update: function () {
                var self = this;
                this.now = new Date();
                $.ajax({ url: path + "feed/list.json", dataType: 'json', success: function (feeds) {
                    var by_name = {};
                    for (var z in feeds) by_name[feeds[z].name] = feeds[z];
                    for (var key in FEEDS) {
                        var f = by_name[FEEDS[key]];
                        self[key] = (f && f.value !== null && !isNaN(f.value)) ? f.value * 1 : false;
                    }
                    var room = by_name[FEEDS.room];
                    self.live = !!(room && Date.now() / 1000 - room.time < 300);
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
