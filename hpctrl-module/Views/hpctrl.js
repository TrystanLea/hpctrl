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

// Sensors are emoncms feeds.
// role: read by the hpctrl service (service/sensors.py), which treats a value older than stale (s, default
//   600) as missing. Only used once chosen: a feed found by name is offered as a suggestion.
// display: shown on the main page. Without a saved choice the first feed found by name is shown.
var SENSORS = [
    { key: 'room', role: 'room', display: true, required: true, stale: 1800, unit: '°C', icon: 'svg-icon-home',
      label: 'Room temperature', names: ['heatpump_roomT', 'room_temperature', 'roomT'],
      description: 'Thermostat, shown on the dial. If stale the service assumes 10° and heats' },
    { key: 'flow', role: 'flow', display: true, required: true, unit: '°C', icon: 'svg-icon-radiator',
      label: 'Flow temperature', names: ['heatpump_flowT'],
      description: 'Control waits while this is missing' },
    { key: 'return', role: 'return', required: true, unit: '°C', icon: 'svg-icon-radiator',
      label: 'Return temperature', names: ['heatpump_returnT'],
      description: 'Sets the flow target in Min mode' },
    { key: 'flowrate', role: 'flowrate', required: true, unit: '', icon: 'svg-icon-refresh-cw',
      label: 'Flow rate', names: ['heatpump_flowrate'],
      description: 'Above zero at service start means the heat pump is already heating' },
    { key: 'cyl_top', role: 'cyl_top', dhw: true, unit: '°C', icon: 'svg-icon-shower',
      label: 'Cylinder top', names: ['cyl_top', 'cylinder_top'],
      description: 'A hot water run ends when the top reaches its target' },
    { key: 'cyl_bot', role: 'cyl_bot', dhw: true, unit: '°C', icon: 'svg-icon-shower',
      label: 'Cylinder bottom', names: ['cyl_bot', 'cylinder_bottom'],
      description: '...and the bottom is within 3°. Sets the hot water flow target in Min mode' },
    { key: 'outside', role: 'ambient', display: true, unit: '°C', icon: 'svg-icon-earth',
      label: 'Outside temperature', names: ['heatpump_outsideT', 'heatpump_ambient'],
      description: 'Shown on the main page and logged by the service' },
    { key: 'extpipe', role: 'extpipe', unit: '°C', icon: 'svg-icon-snowflake',
      label: 'External pipe', names: [],
      description: 'Frost protection cycles the pump below 4°. Not used: no frost protection' },
    { key: 'elec', display: true, unit: 'W', icon: 'svg-icon-smartmeter',
      label: 'Electric input', names: ['heatpump_elec'],
      description: 'Heat pump electric power' },
    { key: 'heat', display: true, unit: 'W', icon: 'svg-icon-sun',
      label: 'Heat output', names: ['heatpump_heat'],
      description: 'Heat pump heat output, with electric input gives COP' }
];
var VIRTUAL_FEED = 7;  // engine: values computed on demand, nothing in Redis for the service to read

// Control parameters, set in the service (service/controller.py PARAMS, LIMITS).
// scale: shown in minutes, stored in seconds.
var PARAM_GROUPS = [
    { label: 'Thermostat', params: [
        { key: 'hysteresis', label: 'Hysteresis', unit: '°', step: 0.05,
          description: 'Heating starts below set point minus this, stops above set point plus this' },
        { key: 'room_fallback', label: 'Stale room temperature', unit: '°', step: 0.5,
          description: 'Assumed when the room sensor is stale. Below the set point keeps heating on' }
    ]},
    { label: 'Min mode flow', curve: true, params: [
        { key: 'ratchet_after', label: 'Hold after', unit: 'min', scale: 60, step: 1,
          description: 'From this long into a heating cycle the flow target can only rise, so defrosts don\'t pull it down' }
    ]},
    { label: 'Start and stop', params: [
        { key: 'idle_flowT', label: 'Idle flow target', unit: '°', step: 0.5,
          description: 'Flow target while starting and stopping' },
        { key: 'start_hold', label: 'Start hold', unit: 's', step: 5,
          description: 'Idle flow target for this long after the pump starts' },
        { key: 'stop_delay', label: 'Stop delay', unit: 's', step: 5,
          description: 'At set point: idle flow target for this long, then pump off' },
        { key: 'stop_hold', label: 'Stop hold', unit: 's', step: 5,
          description: 'Then wait this long before heating can start again' }
    ]},
    { label: 'Hot water', dhw: true, params: [
        { key: 'dhw_dT', label: 'Flow above cylinder', unit: '°', step: 0.5,
          description: 'Min mode flow target above cylinder bottom. Max mode without a flow temperature: above the target' },
        { key: 'dhw_bottom_margin', label: 'Bottom margin', unit: '°', step: 0.5,
          description: 'A run ends when the top reaches the target and the bottom is within this of it' },
        { key: 'dhw_heating_delay', label: 'Heating pause', unit: 's', step: 10,
          description: 'Space heating waits this long after a hot water run' },
        { key: 'dhw_window', label: 'Start window', unit: 'min', scale: 60, step: 1,
          description: 'A run starts if the service sees its start time within this window, once a day' }
    ]},
    { label: 'Frost protection', params: [
        { key: 'frost_temperature', label: 'Pipe temperature', unit: '°', step: 0.5,
          description: 'Pump cycles while the external pipe is below this and heating is off' },
        { key: 'frost_off_interval', label: 'Off for', unit: 'min', scale: 60, step: 1,
          description: 'Pump comes on after this long off' },
        { key: 'frost_on_duration', label: 'On for', unit: 'min', scale: 60, step: 1,
          description: 'and runs for this long' },
        { key: 'frost_flowT', label: 'Flow target', unit: '°', step: 0.5,
          description: 'Flow target while circulating' }
    ]}
];

var DIAL_DEFAULTS = { dial_min: 5, dial_max: 25, dial_step: 0.1 };

// Type-to-filter picker for feeds.
// options: [{ value, label, group, detail }]; group is the node or tag, shown as group:label
var HpPicker = {
    props: { options: Array, value: String, placeholder: String },
    emits: ['pick'],
    data: function () {
        return { open: false, query: '', cursor: 0 };
    },
    computed: {
        selected: function () {
            var value = this.value;
            return this.options.find(function (o) { return o.value === value; }) || null;
        },
        filtered: function () {
            var terms = this.query.toLowerCase().split(/\s+/).filter(Boolean);
            return this.options.filter(function (o) {
                var text = HpPicker.text(o).toLowerCase();
                return terms.every(function (t) { return text.indexOf(t) >= 0; });
            });
        },
        // Options with a header row at each change of group
        rows: function () {
            var rows = [], group = null;
            this.filtered.forEach(function (o, index) {
                if (o.group && o.group !== group) rows.push({ header: o.group });
                group = o.group;
                rows.push({ option: o, index: index });
            });
            return rows;
        }
    },
    methods: {
        show: function () {
            var value = this.value;
            this.open = true;
            this.query = '';
            this.cursor = Math.max(0, this.filtered.findIndex(function (o) { return o.value === value; }));
            this.$nextTick(this.scroll);
        },
        hide: function () {
            this.open = false;
        },
        choose: function (option) {
            if (option.value !== this.value) this.$emit('pick', option.value);
            this.open = false;
            this.$refs.input.blur();
        },
        key: function (e) {
            if (!this.open) return;
            if (e.key == 'ArrowDown' || e.key == 'ArrowUp') {
                e.preventDefault();
                var n = this.filtered.length;
                if (n) this.cursor = (this.cursor + (e.key == 'ArrowDown' ? 1 : n - 1)) % n;
                this.$nextTick(this.scroll);
            } else if (e.key == 'Enter') {
                e.preventDefault();
                if (this.filtered[this.cursor]) this.choose(this.filtered[this.cursor]);
            } else if (e.key == 'Escape') {
                this.$refs.input.blur();
            }
        },
        scroll: function () {
            var el = this.$refs.list && this.$refs.list.querySelector('.is-cursor');
            if (el) el.scrollIntoView({ block: 'nearest' });
        },
        text: function (o) {
            return HpPicker.text(o);
        }
    },
    text: function (o) {
        return o.group ? o.group + ':' + o.label : o.label;
    },
    template: `
<div class="hp-picker" :class="{ 'is-open': open }">
  <input ref="input" type="text" class="form-select form-select-sm" autocomplete="off" spellcheck="false"
         :placeholder="open ? 'Type to filter' : placeholder"
         :value="open ? query : (selected ? text(selected) : '')"
         @focus="show" @blur="hide" @keydown="key" @input="query = $event.target.value; cursor = 0"/>
  <div class="hp-picker-list" v-if="open" ref="list">
    <template v-for="row in rows">
      <div v-if="row.header" class="hp-picker-group">{{ row.header }}</div>
      <div v-else class="hp-picker-option" :class="{ 'is-cursor': row.index == cursor, 'is-selected': row.option.value === value }"
           @mousedown.prevent="choose(row.option)" @mousemove="cursor = row.index">
        <span class="hp-picker-label">{{ row.option.label }}</span>
        <span class="hp-picker-detail">{{ row.option.detail }}</span>
      </div>
    </template>
    <div v-if="!filtered.length" class="hp-picker-empty">No match</div>
  </div>
</div>`
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
                sensor_defs: SENSORS.filter(function (d) { return dhw_enable || !d.dhw; }),
                feeds: [],
                feeds_loaded: false,
                param_groups: PARAM_GROUPS.filter(function (g) { return dhw_enable || !g.dhw; }),
                param_edits: {},
                command_pending: '',
                status: null,
                status_age: 0,
                events: [],
                show_all_events: false,
                room_history: [],      // [[time ms, value]] from midnight, 5 min averages
                history_key: '',       // feed id and day the history was loaded for
                history_time: 0,
                hover: null,
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
            sensor_rows: function () {
                var self = this;
                return this.sensor_defs.map(function (def) {
                    var choice = self.settings[def.key];
                    var match = self.match(def);
                    var feed = choice ? self.feeds_by_id[choice] || false : (choice === undefined && !def.role ? match : false);
                    var state;
                    if (choice && !feed) state = 'miss';  // chosen, but no longer in the feed list
                    else if (feed) state = self.feed_stale(feed, def) ? 'stale' : (choice === undefined ? 'auto' : 'ok');
                    else if (choice === 0) state = 'off';
                    else state = def.role && (def.required || def.dhw) ? 'miss' : 'off';
                    return {
                        def: def, feed: feed, state: state,
                        choice: choice === undefined ? (def.role ? '' : 'auto') : String(choice),
                        suggestion: def.role && choice === undefined && match && match.engine != VIRTUAL_FEED ? match : false
                    };
                });
            },
            sensors_connected: function () {
                return this.sensor_rows.filter(function (r) { return r.feed; }).length;
            },
            suggestions: function () {
                return this.sensor_rows.filter(function (r) { return r.suggestion; });
            },
            status_live: function () {
                return !!this.status && this.status_age < 60;
            },
            service_text: function () {
                if (!this.status) return 'No service';
                if (!this.status_live) return 'Offline';
                return this.status.dry_run ? 'Dry run' : 'Running';
            },
            params_live: function () {
                return this.status_live && !!this.status.params;
            },
            // Min mode flow target now, from the curve being edited and the return temperature the service sees
            curve_preview: function () {
                var ret = this.status && this.status.sensors && this.status.sensors['return'];
                if (!this.params_live || !ret || ret.value === null) return '';
                var rT1 = this.param('min_rT1'), dT1 = this.param('min_dT1'), rT2 = this.param('min_rT2'), dT2 = this.param('min_dT2');
                if (rT1 == rT2) return '';
                var dT = dT1 + (dT2 - dT1) * (ret.value - rT1) / (rT2 - rT1);
                var flow = ret.value + dT;
                return 'Return now ' + ret.value.toFixed(1) + '° + ' + dT.toFixed(1) + '° = ' + flow.toFixed(1) + '°, sent as ' + (Math.ceil(flow * 0.5) * 2) + '°';
            },
            params_modified: function () {
                var self = this;
                if (!this.params_live) return 0;
                return Object.keys(this.status.param_defaults).filter(function (k) { return self.param_modified(k); }).length;
            },
            // Commands the Ecodan hasn't confirmed
            verify_issues: function () {
                var v = this.status_live && this.status.verify, out = [];
                if (!v) return out;
                var names = { power: 'pump', flowT: 'flow temperature' };
                for (var field in v) {
                    if (v[field].state == 'resending' || v[field].state == 'failed') {
                        out.push('Ecodan ' + (names[field] || field) + ' is ' + v[field].reported + ', sent ' + v[field].sent +
                                 (v[field].state == 'failed' ? ': not confirmed after resending' : ': resending'));
                    }
                }
                return out;
            },
            dhw_running: function () {
                return this.status_live && this.status.mode == 'dhw';
            },
            waiting_for_sensors: function () {
                return this.status_live && this.status.label == 'Waiting';
            },
            events_shown: function () {
                return this.show_all_events ? this.events : this.events.slice(0, 8);
            },
            // Live values, false when no feed or no value
            room: function () { return this.live_value('room'); },
            flow: function () { return this.live_value('flow'); },
            outside: function () { return this.live_value('outside'); },
            elec: function () { return this.live_value('elec'); },
            heat: function () { return this.live_value('heat'); },
            live: function () {
                return !this.feed_stale(this.resolve(SENSORS[0]), SENSORS[0]);
            },
            ready: function () {
                return !this.sensor_rows.some(function (r) { return r.state == 'miss'; });
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
            // From the service when it's running, else a guess with the same 0.1 hysteresis
            heating: function () {
                if (this.status_live) return this.status.state == 1 && this.status.mode == 'heating';
                return this.room !== false && this.room <= this.set_point - 0.1;
            },
            state_text: function () {
                if (this.status_live) return this.status.label;
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
                        height: self.level(sp),
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
            // Room temperature since midnight as SVG paths on the profile's 1440 x 100 box, broken at gaps.
            // The live value continues the line to the now marker.
            room_paths: function () {
                var self = this;
                var midnight = new Date(this.now).setHours(0, 0, 0, 0);
                var points = this.room_history.slice();
                if (this.room !== false) points.push([this.now.getTime(), this.room]);
                var paths = [], d = '';
                points.forEach(function (p) {
                    if (p[1] === null || isNaN(p[1])) {
                        if (d) paths.push(d);
                        d = '';
                        return;
                    }
                    var x = (p[0] - midnight) / 60000;
                    var y = 100 - self.level(p[1]);
                    d += (d ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(2);
                });
                if (d) paths.push(d);
                return paths;
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
            // Height on the day profile, % from the bottom: set point bars and the room line share it
            level: function (t) {
                return 18 + 82 * this.clamp((t - this.t_min) / (this.t_max - this.t_min), 0, 1);
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
            // First feed found by one of the sensor's names
            match: function (def) {
                for (var i = 0; i < def.names.length; i++) {
                    var match = this.feeds.find(function (f) { return f.name == def.names[i]; });
                    if (match) return match;
                }
                return false;
            },
            // Feed shown on the main page: saved choice, else a name match
            resolve: function (def) {
                var choice = this.settings[def.key];
                if (choice === 0) return false;
                if (choice !== undefined) return this.feeds_by_id[choice] || false;
                return this.match(def);
            },
            live_value: function (key) {
                var f = this.resolve(SENSORS.find(function (d) { return d.key == key; }));
                return (f && f.value !== null && !isNaN(f.value)) ? f.value * 1 : false;
            },
            sensor_options: function (row) {
                var self = this, def = row.def;
                var out = [];
                if (!def.role) out.push({ value: 'auto', label: 'Auto (' + def.names.join(', ') + ')' });
                if (!def.required) out.push({ value: '0', label: 'Not used' });
                if (row.state == 'miss' && row.choice) out.push({ value: row.choice, label: 'Feed ' + row.choice + ' (not found)' });
                this.feed_groups.forEach(function (group) {
                    group.feeds.forEach(function (f) {
                        if (def.role && f.engine == VIRTUAL_FEED) return;
                        out.push({ value: String(f.id), label: f.name, group: group.tag, detail: self.feed_value(f, def.unit) });
                    });
                });
                return out;
            },
            set_sensor: function (def, value) {
                if (value == 'auto') delete this.settings[def.key];
                else this.settings[def.key] = value * 1;
                this.save_settings(!!def.role);
            },
            use_suggestions: function () {
                var self = this;
                this.suggestions.forEach(function (r) { self.settings[r.def.key] = r.suggestion.id * 1; });
                this.save_settings(true);
            },

            // Control parameters: shown from the service, edits held until it reports them
            param: function (key) {
                if (this.param_edits[key] !== undefined) return this.param_edits[key];
                return this.status && this.status.params ? this.status.params[key] : undefined;
            },
            param_shown: function (def) {
                var v = this.param(def.key);
                return v === undefined ? '' : +(v / (def.scale || 1)).toFixed(2);
            },
            param_default: function (def) {
                var d = this.status && this.status.param_defaults ? this.status.param_defaults[def.key] : undefined;
                return d === undefined ? '' : +(d / (def.scale || 1)).toFixed(2) + (def.unit == '°' ? '°' : ' ' + def.unit);
            },
            param_modified: function (key) {
                var d = this.status && this.status.param_defaults;
                return !!d && this.param(key) !== undefined && Math.abs(this.param(key) - d[key]) > 1e-9;
            },
            set_param: function (key, shown, scale) {
                var value = parseFloat(shown);
                if (isNaN(value) || !this.params_live) return;
                value = value * (scale || 1);
                var limits = this.status.param_limits[key];
                if (limits) value = this.clamp(value, limits[0], limits[1]);
                this.param_edits[key] = value;
                this.save_params();
            },
            reset_params: function () {
                this.param_edits = {};
                this.save_params(true);
            },
            // Only values that differ from the defaults are sent
            save_params: function (reset) {
                var self = this;
                var params = {};
                if (!reset) {
                    Object.keys(this.status.param_defaults).forEach(function (k) {
                        if (self.param_modified(k)) params[k] = self.param(k);
                    });
                } else {
                    this.status.params = Object.assign({}, this.status.param_defaults);
                }
                this.settings_state = 'saving';
                $.ajax({
                    method: "POST", url: path + "hpctrl/set-params", dataType: 'json',
                    data: { params: JSON.stringify(params) },
                    success: function (result) {
                        self.settings_state = (result && result.success) ? 'saved' : 'error';
                    },
                    error: function () { self.settings_state = 'error'; },
                    complete: function () {
                        clearTimeout(settings_timer);
                        if (self.settings_state == 'saved') {
                            settings_timer = setTimeout(function () { self.settings_state = ''; }, 2500);
                        }
                    }
                });
            },

            // Manual hot water run
            command: function (cmd) {
                var self = this;
                this.command_pending = cmd;
                $.ajax({
                    method: "POST", url: path + "hpctrl/command", dataType: 'json', data: { cmd: cmd },
                    success: function (result) {
                        if (!result || !result.success) self.command_pending = '';
                    },
                    error: function () { self.command_pending = ''; }
                });
                // Cleared when the service reports the change, or after 30 s
                setTimeout(function () { if (self.command_pending == cmd) self.command_pending = ''; }, 30000);
            },

            set_dial: function (key, value) {
                value = parseFloat(value);
                if (isNaN(value)) return;
                this.settings[key] = value;
                this.save_settings();
            },
            feed_value: function (feed, unit) {
                if (!feed || feed.value === null || isNaN(feed.value)) return '--';
                if (unit == 'W') return (feed.value * 1).toFixed(0) + ' W';
                return (feed.value * 1).toFixed(unit ? 1 : 2) + unit;
            },
            feed_age: function (feed) {
                if (!feed || !feed.time) return '';
                return this.ago(this.now.getTime() / 1000 - feed.time) + ' ago';
            },
            ago: function (s) {
                s = Math.max(0, Math.round(s));
                if (s < 60) return s + 's';
                if (s < 3600) return Math.round(s / 60) + ' min';
                if (s < 86400) return Math.round(s / 3600) + ' h';
                return Math.round(s / 86400) + ' days';
            },
            feed_stale: function (feed, def) {
                return !feed || this.now.getTime() / 1000 - feed.time > ((def && def.stale) || 600);
            },
            // publish: also send the sensor feeds to the service
            save_settings: function (publish) {
                var self = this;
                this.settings_state = 'saving';
                $.ajax({
                    method: "POST", url: path + "hpctrl/set-settings", dataType: 'json',
                    data: { settings: JSON.stringify(this.settings), publish_sensors: publish === true ? 1 : '' },
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
            event_time: function (time) {
                var d = new Date(time * 1000);
                var hm = this.pad(d.getHours()) + ':' + this.pad(d.getMinutes());
                if (d.toDateString() == this.now.toDateString()) return hm;
                return d.toLocaleDateString(undefined, { weekday: 'short' }) + ' ' + hm;
            },
            close_settings: function () {
                if (!this.ready) return;
                this.view = 'control';
                window.scrollTo(0, 0);
            },

            // Room feed since midnight, reloaded every 5 min and when the feed or day changes
            load_history: function () {
                var self = this;
                var feed = this.resolve(SENSORS[0]);
                if (!feed) {
                    this.room_history = [];
                    return;
                }
                var key = feed.id + ':' + this.now.toDateString();
                if (key == this.history_key && Date.now() - this.history_time < 300000) return;
                this.history_key = key;
                this.history_time = Date.now();
                var start = new Date(this.now).setHours(0, 0, 0, 0);
                $.ajax({
                    url: path + "feed/data.json", dataType: 'json', cache: false,
                    data: { id: feed.id, start: start, end: Date.now(), interval: 300, average: 1, skipmissing: 0 },
                    success: function (data) {
                        if (Array.isArray(data) && key == self.history_key) self.room_history = data;
                    }
                });
            },
            // Readout under the pointer: room temperature and set point at that time
            profile_hover: function (e) {
                var box = e.currentTarget.getBoundingClientRect();
                var minute = this.clamp((e.clientX - box.left) / box.width, 0, 1) * 1440;
                if (minute > this.now_minutes) {
                    this.hover = null;
                    return;
                }
                var midnight = new Date(this.now).setHours(0, 0, 0, 0);
                var t = midnight + minute * 60000;
                var best = null;
                this.room_history.forEach(function (p) {
                    if (p[1] !== null && (!best || Math.abs(p[0] - t) < Math.abs(best[0] - t))) best = p;
                });
                if (this.room !== false && (!best || Math.abs(this.now.getTime() - t) < Math.abs(best[0] - t))) best = [this.now.getTime(), this.room];
                if (!best || Math.abs(best[0] - t) > 900000) {
                    this.hover = null;
                    return;
                }
                var m = Math.round((best[0] - midnight) / 60000);
                var list = this.schedule.heating, sp = list[list.length - 1].set_point;
                for (var i = 0; i < list.length; i++) if (m >= this.minutes(list[i].start)) sp = list[i].set_point;
                this.hover = {
                    left: m / 14.4, bottom: this.level(best[1]),
                    text: this.pad(Math.floor(m / 60)) + ':' + this.pad(m % 60) + '  ' + (best[1] * 1).toFixed(1) + '°  set ' + (sp * 1).toFixed(1) + '°'
                };
            },
            load_status: function () {
                var self = this;
                $.ajax({ url: path + "hpctrl/status.json", dataType: 'json', cache: false, success: function (result) {
                    if (!result || !result.success) return;
                    self.status = result.status;
                    self.status_age = result.status ? result.time - result.status.time : 0;
                    if (result.status && result.status.params) {
                        // Drop edits the service has taken up
                        for (var key in self.param_edits) {
                            if (Math.abs(result.status.params[key] - self.param_edits[key]) < 1e-9) delete self.param_edits[key];
                        }
                    }
                    if (self.command_pending == 'dhw_start' && self.dhw_running) self.command_pending = '';
                    if (self.command_pending == 'dhw_stop' && !self.dhw_running) self.command_pending = '';
                    self.events = (result.events || []).filter(function (e) { return e; });
                }});
            },

            // Live values
            update: function () {
                var self = this;
                this.now = new Date();
                this.load_status();
                $.ajax({ url: path + "feed/list.json", dataType: 'json', cache: false, success: function (feeds) {
                    if (!Array.isArray(feeds)) return;
                    self.feeds = feeds;
                    self.load_history();
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
    }).component('hp-picker', HpPicker).mount('#hpctrl');
}
