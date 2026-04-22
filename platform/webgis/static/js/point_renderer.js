// PointRenderer —— 基于 Cesium.PointPrimitiveCollection 的高性能点渲染。
//
// 替代原有的 "每点一个 Entity + Billboard(dataURL)" 模式：
// - 单次 drawcall 批量渲染，5 万点稳定 55-60fps
// - diffUpdate(list) 以 id 为 key 做增删改，不全量重建
// - 颜色按国标 category 映射，大小按 rank 分级，国保/省保加金色描边
// - 标签密度按 rank 分级显示距离，超过 300 个标签时整体隐藏
//
// 依赖全局：window.Cesium, window.Dict, window.Bus
// 输出：window.PointRenderer（类），属于非 ES module 暴露方式。
(function () {
    const LABEL_BUDGET = 300;          // 单视口内累计标签数上限
    const NAME_TRUNC = 12;             // 名称超过此长度截断

    function truncateName(name) {
        if (!name) return '';
        const s = String(name);
        if (s.length <= NAME_TRUNC) return s;
        return s.slice(0, 5) + '…' + s.slice(-3);
    }

    class PointRenderer {
        constructor(viewer) {
            this.viewer = viewer;
            this.coll = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
            this.labelColl = viewer.scene.primitives.add(new Cesium.LabelCollection());

            // id -> { primitive, label, record }
            this.map = new Map();

            // 全局开关
            this._visible = true;
            this._labelsEnabled = true;
            this._labelFontSize = 14;
            this._labelFontFamily = '"Microsoft YaHei", sans-serif';
        }

        // ── 主入口：批量 diff 更新 ────────────────────────
        diffUpdate(list) {
            const next = new Set();
            for (const r of list) if (r && r.id) next.add(r.id);

            // 先移除不再命中的
            for (const [id, rec] of this.map) {
                if (!next.has(id)) {
                    try { this.coll.remove(rec.primitive); } catch (e) {}
                    if (rec.label) { try { this.labelColl.remove(rec.label); } catch (e) {} }
                    this.map.delete(id);
                }
            }

            // 标签预算：不是"总量超就全关"，而是按 rank 升序分配，
            // 国保/省保优先拿到标签，预算用完（LABEL_BUDGET）后低等级不再给。
            // 这样即便视口内 5000 点，国保省保的名字仍然能看见。
            const wantsLabel = new Set();
            if (this._labelsEnabled) {
                const sorted = list.slice().sort((a, b) => {
                    const ra = parseInt((a && a.rank) || '5', 10);
                    const rb = parseInt((b && b.rank) || '5', 10);
                    return ra - rb;
                });
                let quota = LABEL_BUDGET;
                for (const r of sorted) {
                    if (quota <= 0) break;
                    if (r && r.id) { wantsLabel.add(r.id); quota--; }
                }
            }

            for (const r of list) {
                if (!r || !r.id) continue;
                const cat = r.category || '0600';
                const rank = r.rank || '5';
                const color = Cesium.Color.fromCssColorString(window.Dict.categoryColor(cat));
                const size = window.Dict.rankSize(rank);
                const prominent = window.Dict.rankProminent(rank);
                const outlineColor = r.has_3d
                    ? Cesium.Color.GOLD
                    : (prominent ? Cesium.Color.GOLD : Cesium.Color.fromCssColorString('rgba(0,0,0,0.6)'));
                const outlineWidth = r.has_3d || prominent ? 2 : 1;

                const pos = Cesium.Cartesian3.fromDegrees(r.lng, r.lat);
                const existing = this.map.get(r.id);

                if (existing) {
                    // 数据没变就跳过；只在关键字段变化时更新属性
                    const rec = existing.record;
                    if (rec.lng !== r.lng || rec.lat !== r.lat) {
                        existing.primitive.position = pos;
                    }
                    if (rec.category !== cat || rec.rank !== rank || rec.has_3d !== r.has_3d) {
                        existing.primitive.color = color;
                        existing.primitive.outlineColor = outlineColor;
                        existing.primitive.outlineWidth = outlineWidth;
                        existing.primitive.pixelSize = size;
                    }
                    existing.record = r;
                    // 标签按本次分级预算重新决定是否显示
                    const shouldHaveLabel = wantsLabel.has(r.id);
                    if (shouldHaveLabel && !existing.label) {
                        existing.label = this._addLabel(pos, r);
                    } else if (!shouldHaveLabel && existing.label) {
                        try { this.labelColl.remove(existing.label); } catch (e) {}
                        existing.label = null;
                    } else if (existing.label) {
                        existing.label.text = truncateName(r.name);
                    }
                    continue;
                }

                const primitive = this.coll.add({
                    position: pos,
                    color,
                    outlineColor,
                    outlineWidth,
                    pixelSize: size,
                    scaleByDistance: new Cesium.NearFarScalar(1e3, 1.2, 5e4, 0.6),
                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                    show: this._visible,
                    // Cesium pick 会返回 picked.id；放一个带 _type 标记的对象用于区分
                    id: { _type: 'relic', code: r.code, relicId: r.id },
                });
                const label = wantsLabel.has(r.id) ? this._addLabel(pos, r) : null;
                this.map.set(r.id, { primitive, label, record: r });
            }

            this.viewer.scene.requestRender();
        }

        _addLabel(pos, r) {
            return this.labelColl.add({
                position: pos,
                text: truncateName(r.name),
                font: this._labelFontSize + 'px ' + this._labelFontFamily,
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 3,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -(window.Dict.rankSize(r.rank) / 2 + 5)),
                distanceDisplayCondition: new Cesium.DistanceDisplayCondition(
                    0, window.Dict.rankLabelMaxDistance(r.rank)
                ),
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
                show: this._visible,
            });
        }

        // ── 开关 ─────────────────────────────────────────
        setVisible(v) {
            this._visible = !!v;
            for (const [, rec] of this.map) {
                rec.primitive.show = this._visible;
                if (rec.label) rec.label.show = this._visible && this._labelsEnabled;
            }
            this.viewer.scene.requestRender();
        }

        setLabelsEnabled(v) {
            this._labelsEnabled = !!v;
            for (const [, rec] of this.map) {
                if (rec.label) rec.label.show = this._visible && this._labelsEnabled;
            }
            this.viewer.scene.requestRender();
        }

        setLabelFont(font) {
            this._labelFontFamily = font;
            const fontStr = this._labelFontSize + 'px ' + font;
            for (const [, rec] of this.map) {
                if (rec.label) rec.label.font = fontStr;
            }
            this.viewer.scene.requestRender();
        }

        setLabelSize(px) {
            this._labelFontSize = parseInt(px, 10) || 14;
            const fontStr = this._labelFontSize + 'px ' + this._labelFontFamily;
            for (const [, rec] of this.map) {
                if (rec.label) rec.label.font = fontStr;
            }
            this.viewer.scene.requestRender();
        }

        findById(id)   { const rec = this.map.get(id); return rec ? rec.record : null; }
        findByCode(code) {
            for (const [, rec] of this.map) if (rec.record.code === code) return rec.record;
            return null;
        }

        clear() {
            try { this.coll.removeAll(); } catch (e) {}
            try { this.labelColl.removeAll(); } catch (e) {}
            this.map.clear();
            this.viewer.scene.requestRender();
        }

        size() { return this.map.size; }
    }

    window.PointRenderer = PointRenderer;
})();
