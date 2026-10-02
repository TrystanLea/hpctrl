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

// Control inputs: emoncms inputs read by the hpctrl service. Values older than
// stale (s) are treated as missing, as service/inputs.py.
var INPUTS = [
    { key: 'in_room',     role: 'room',     label: 'Room temperature',     unit: '°C', required: true, icon: 'svg-icon-home', stale: 1800,
      description: 'Thermostat. If stale the service assumes 10° and heats' },
    { key: 'in_flow',     role: 'flow',     label: 'Flow temperature',     unit: '°C', required: true, icon: 'svg-icon-radiator',
      description: 'Control waits while this is missing' },
    { key: 'in_return',   role: 'return',   label: 'Return temperature',   unit: '°C', required: true, icon: 'svg-icon-radiator',
      description: 'Sets the flow target in Min mode' },
    { key: 'in_flowrate', role: 'flowrate', label: 'Flow rate',            unit: '', required: true, icon: 'svg-icon-refresh-cw',
      description: 'Above zero at service start means the heat pump is already heating' },
    { key: 'in_cyl_top',  role: 'cyl_top',  label: 'Cylinder top',         unit: '°C', dhw: true, icon: 'svg-icon-shower',
      description: 'Hot water run ends when top reaches target' },
    { key: 'in_cyl_bot',  role: 'cyl_bot',  label: 'Cylinder bottom',      unit: '°C', dhw: true, icon: 'svg-icon-shower',
      description: '...and bottom is within 3°. Sets the hot water flow target in Min mode' },
    { key: 'in_ambient',  role: 'ambient',  label: 'Outside temperature',  unit: '°C', icon: 'svg-icon-earth',
      description: 'Logged only' },
    { key: 'in_extpipe',  role: 'extpipe',  label: 'External pipe',        unit: '°C', icon: 'svg-icon-snowflake',
      description: 'Frost protection cycles the pump below 4°. Not used: no frost protection' }
];
var INPUT_STALE = 600;

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
                input_defs: INPUTS.filter(function (d) { return dhw_enable || !d.dhw; }),
                inputs: [],
                inputs_loaded: false,
                status: null,
                status_age: 0,
                events: [],
                show_all_events: false,
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
            inputs_by_id: function () {
                var out = {};
                this.inputs.forEach(function (i) { out[i.id] = i; });
                return out;
            },
            // Input list grouped by node for the pickers
            input_groups: function () {
                var groups = {};
                this.inputs.forEach(function (i) {
                    var node = i.nodeid || 'No node';
                    if (!groups[node]) groups[node] = [];
                    groups[node].push(i);
                });
                return Object.keys(groups).sort().map(function (node) {
                    return { node: node, inputs: groups[node].sort(function (a, b) { return a.name.localeCompare(b.name); }) };
                });
            },
            input_rows: function () {
                var self = this;
                return this.input_defs.map(function (def) {
                    var choice = self.input_choice(def);
                    var input = choice ? self.inputs_by_id[choice] || false : false;
                    var state;
                    if (input) state = self.input_stale(input, def) ? 'stale' : 'ok';
                    else if (choice) state = 'miss';  // chosen, but not in the input list
                    else if (choice === 0) state = 'off';
                    else state = def.required || def.dhw ? 'miss' : 'off';
                    return { def: def, input: input, state: state, choice: choice === undefined ? '' : String(choice) };
                });
            },
            inputs_connected: function () {
                return this.input_rows.filter(function (r) { return r.input; }).length;
            },
            // Feeds for the display, inputs for the service
            ready_count: function () {
                return this.feeds_connected + this.inputs_connected;
            },
            ready_total: function () {
                return this.feed_defs.length + this.input_defs.length;
            },
            status_live: function () {
                return !!this.status && this.status_age < 60;
            },
            service_text: function () {
                if (!this.status) return 'No service';
                if (!this.status_live) return 'Offline';
                return this.status.dry_run ? 'Dry run' : 'Running';
            },
            waiting_for_inputs: function () {
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
                return !this.feed_stale(this.resolve(FEEDS[0]));
            },
            ready: function () {
                if (this.feed_rows.some(function (r) { return r.state == 'miss'; })) return false;
                return !this.inputs_loaded || !this.input_rows.some(function (r) { return r.state == 'miss'; });
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
            // Saved choice, else the input the service is using now
            input_choice: function (def) {
                var choice = this.settings[def.key];
                if (choice !== undefined) return choice;
                var used = this.status && this.status.inputs && this.status.inputs[def.role];
                return used ? used.id : undefined;
            },
            input_stale: function (input, def) {
                return !input.time || this.now.getTime() / 1000 - input.time > (def.stale || INPUT_STALE);
            },
            input_value: function (input, def) {
                if (!input || input.value === null || isNaN(input.value)) return '--';
                return (input.value * 1).toFixed(def.unit ? 1 : 2) + (def.unit ? def.unit : '');
            },
            // The service gets the whole mapping, so save the inputs in use now along with the change
            set_input: function (key, value) {
                var self = this;
                this.input_defs.forEach(function (def) {
                    var choice = self.input_choice(def);
                    if (self.settings[def.key] === undefined && choice !== undefined) self.settings[def.key] = choice;
                });
                this.settings[key] = value * 1;
                this.save_settings();
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
                return this.ago(this.now.getTime() / 1000 - feed.time) + ' ago';
            },
            ago: function (s) {
                s = Math.max(0, Math.round(s));
                if (s < 60) return s + 's';
                if (s < 3600) return Math.round(s / 60) + ' min';
                if (s < 86400) return Math.round(s / 3600) + ' h';
                return Math.round(s / 86400) + ' days';
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
                this.load_inputs();
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

            load_inputs: function () {
                var self = this;
                $.ajax({ url: path + "input/list.json", dataType: 'json', cache: false, success: function (inputs) {
                    if (!Array.isArray(inputs)) return;
                    self.inputs = inputs;
                    self.inputs_loaded = true;
                }});
            },
            load_status: function () {
                var self = this;
                $.ajax({ url: path + "hpctrl/status.json", dataType: 'json', cache: false, success: function (result) {
                    if (!result || !result.success) return;
                    self.status = result.status;
                    self.status_age = result.status ? result.time - result.status.time : 0;
                    self.events = (result.events || []).filter(function (e) { return e; });
                }});
            },

            // Live values
            update: function () {
                var self = this;
                this.now = new Date();
                this.load_status();
                if (this.view == 'settings') this.load_inputs();
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
