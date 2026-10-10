/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 * Copyright (C) 2026 DB Score contributors
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as published by the Free Software Foundation.
 */
import QtQuick
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents
import DBScore.Project

Item {
    id: root

    property NavigationSection navigationSection: null
    property int contentNavigationPanelOrderStart: 0

    required property AudioTrackSettingsModel audioModel

    property string bpmInput: ""

    property double audioDuration: audioModel.duration > 0 ? audioModel.duration : 0
    property double scoreDuration: audioModel.scoreDuration > 0 ? audioModel.scoreDuration : 0
    property double totalDuration: Math.max(audioDuration, scoreDuration) + 30.0

    //! NOTE: 缩放比例以「乐谱轨长度」为固定基准，导入音频后不改变整体缩放，
    //! 否则音频变长会让 totalDuration 变大、同样的 zoom 显示更多时间，视觉上像被缩小了。
    property double zoomBaseDuration: scoreDuration + 30.0

    property real zoom: 3.5
    property real scrollSec: 0.0
    property real visibleDuration: Math.max(1.0, zoomBaseDuration / zoom)
    property real maxScroll: Math.max(0.0, totalDuration - visibleDuration)

    property color scoreColor: "#32584B"
    property color audioColor: "#9E5242"
    //! NOTE: 播放指针样式可调（颜色/粗细），仅影响外观，不影响任何功能与同步逻辑。
    property string playheadColor: "#59BA54"
    property real playheadThickness: 1.0
    property var playheadColors: ["#59BA54", "#2F6FED", "#06B6D4", "#E11D48", "#F59E0B", "#111827"]
    property color dimColor: Qt.rgba(0.55, 0.60, 0.57, 0.35)
    property bool prevHasTrack: false

    function pad2(n) {
        return (n < 10 ? "0" : "") + n
    }

    function formatTime(secs) {
        var s = Math.max(0, secs)
        var m = Math.floor(s / 60)
        var sec = Math.floor(s % 60)
        var cs = Math.round((s - Math.floor(s)) * 100)
        if (cs >= 100) {
            cs = 0
            sec += 1
        }
        return pad2(m) + ":" + pad2(sec) + "." + pad2(cs)
    }

    function niceStep(x) {
        if (x <= 0) {
            return 1
        }
        var p = Math.pow(10, Math.floor(Math.log(x) / Math.LN10))
        var r = x / p
        var m = r < 1.5 ? 1 : (r < 3.5 ? 2 : (r < 7.5 ? 5 : 10))
        return m * p
    }

    function repaintTimeline() {
        if (rulerCanvas) { rulerCanvas.requestPaint() }
        if (scoreGridCanvas) { scoreGridCanvas.requestPaint() }
        if (waveCanvas) { waveCanvas.requestPaint() }
    }

    onZoomChanged: repaintTimeline()
    onScrollSecChanged: repaintTimeline()

    Connections {
        target: audioModel
        function onHasTrackChanged() {
            if (audioModel.hasTrack && !prevHasTrack) {
                scrollSec = 0.0
            }
            prevHasTrack = audioModel.hasTrack
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            FlatButton { text: "选择音频"; onClicked: audioModel.chooseFile() }
            FlatButton { text: "替换音频"; enabled: audioModel.hasTrack; onClicked: audioModel.replaceFile() }
            FlatButton { text: "移除伴奏轨"; enabled: audioModel.hasTrack; onClicked: audioModel.remove() }
            FlatButton {
                text: audioModel.metronomeEnabled ? "✓ 节拍器" : "节拍器"
                accentButton: audioModel.metronomeEnabled
                onClicked: audioModel.toggleMetronome()
            }
            FlatButton {
                text: "音频测速"
                enabled: audioModel.hasTrack
                onClicked: audioModel.tapTempo()
            }
            StyledTextLabel {
                text: audioModel.measuredBpm > 0 ? (audioModel.measuredBpm.toFixed(2) + " BPM") : ""
                visible: audioModel.measuredBpm > 0
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            StyledTextLabel { text: "乐谱音量" }
            StyledSlider {
                id: scoreVolumeSlider
                Layout.preferredWidth: 120
                from: -60
                to: 12
                stepSize: 0.5
                onMoved: audioModel.setScoreVolumeDb(value)

                Component.onCompleted: scoreVolumeSlider.value = audioModel.scoreVolumeDb
                Connections {
                    target: audioModel
                    function onScoreVolumeDbChanged() { scoreVolumeSlider.value = audioModel.scoreVolumeDb }
                }
            }

            StyledTextLabel { text: "伴奏轨音量" }
            StyledSlider {
                id: accompanimentVolumeSlider
                Layout.preferredWidth: 120
                from: -60
                to: 12
                stepSize: 0.5
                onMoved: { audioModel.setVolumeDb(value); audioModel.apply() }

                Component.onCompleted: accompanimentVolumeSlider.value = audioModel.volumeDb
                Connections {
                    target: audioModel
                    function onVolumeDbChanged() { accompanimentVolumeSlider.value = audioModel.volumeDb }
                }
            }

            StyledTextLabel { text: "总音量" }
            StyledSlider {
                id: masterVolumeSlider
                Layout.preferredWidth: 120
                from: -60
                to: 12
                stepSize: 0.5
                onMoved: audioModel.setMasterVolumeDb(value)

                Component.onCompleted: masterVolumeSlider.value = audioModel.masterVolumeDb
                Connections {
                    target: audioModel
                    function onMasterVolumeDbChanged() { masterVolumeSlider.value = audioModel.masterVolumeDb }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            StyledTextLabel { text: "设置时间线" }

            Repeater {
                model: root.playheadColors
                Rectangle {
                    width: 16
                    height: 16
                    radius: 3
                    color: modelData
                    border.width: modelData === root.playheadColor ? 2 : 1
                    border.color: modelData === root.playheadColor ? "#333333" : "#C9CFCA"

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.playheadColor = modelData
                    }
                }
            }

            StyledTextLabel { text: "粗细" }
            StyledSlider {
                Layout.preferredWidth: 72
                from: 1
                to: 6
                stepSize: 0.5
                value: root.playheadThickness
                onMoved: root.playheadThickness = value
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            StyledTextLabel { text: "播放位置" }
            StyledSlider {
                Layout.fillWidth: true
                value: audioModel.playbackPosition
                from: 0
                to: Math.max(1, totalDuration)
                onMoved: audioModel.seek(value)
            }
            StyledTextLabel { text: "轨道缩放" }
            StyledSlider {
                id: zoomSlider
                Layout.preferredWidth: 150
                from: 1.0
                to: 6
                stepSize: 0.02
                onMoved: {
                    zoom = value
                    if (scrollSec > maxScroll) {
                        scrollSec = maxScroll
                    }
                }

                Component.onCompleted: zoomSlider.value = zoom
                Connections {
                    target: root
                    function onZoomChanged() { zoomSlider.value = zoom }
                }
            }
            StyledTextLabel { text: Math.round((zoom - 1.0) * 20.0) + "%" }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#F5F7F4"
            radius: 6
            clip: true

            Row {
                anchors.fill: parent

                // 左侧轨道名标签
                Column {
                    width: 86
                    height: parent.height

                    Rectangle {
                        width: parent.width
                        height: 22
                        color: "transparent"
                    }
                    Rectangle {
                        width: parent.width
                        height: (parent.height - 22) / 2
                        color: Qt.rgba(83 / 255, 105 / 255, 93 / 255, 0.14)
                        border.color: "#D9E0DA"

                        Column {
                            anchors.centerIn: parent
                            spacing: 5

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "乐谱轨"
                                color: root.scoreColor
                                font.pixelSize: 11
                                font.bold: true
                            }

                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: 60
                                height: 22
                                radius: 4
                                color: audioModel.scoreMuted ? root.scoreColor : "transparent"
                                border.width: 1
                                border.color: root.scoreColor

                                Text {
                                    anchors.centerIn: parent
                                    text: audioModel.scoreMuted ? "✓ 静音" : "静音"
                                    color: audioModel.scoreMuted ? "#FFFFFF" : root.scoreColor
                                    font.pixelSize: 11
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: audioModel.toggleScoreMute()
                                }
                            }
                        }
                    }
                    Rectangle {
                        width: parent.width
                        height: (parent.height - 22) / 2
                        color: Qt.rgba(158 / 255, 82 / 255, 66 / 255, 0.14)
                        border.color: "#D9E0DA"

                        Column {
                            anchors.centerIn: parent
                            spacing: 5

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "音频轨"
                                color: root.audioColor
                                font.pixelSize: 11
                                font.bold: true
                            }

                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: 60
                                height: 22
                                radius: 4
                                color: audioModel.muted ? root.audioColor : "transparent"
                                border.width: 1
                                border.color: root.audioColor
                                opacity: audioModel.hasTrack ? 1.0 : 0.4

                                Text {
                                    anchors.centerIn: parent
                                    text: audioModel.muted ? "✓ 静音" : "静音"
                                    color: audioModel.muted ? "#FFFFFF" : root.audioColor
                                    font.pixelSize: 11
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    enabled: audioModel.hasTrack
                                    onClicked: {
                                        audioModel.setMuted(!audioModel.muted)
                                        audioModel.apply()
                                    }
                                }
                            }
                        }
                    }
                }

                // 右侧时间线内容
                Item {
                    id: timeline
                    width: parent.width - 86
                    height: parent.height

                    property double pxPerSec: width > 0 ? width / visibleDuration : 0
                    function xAt(t) { return (t - scrollSec) * pxPerSec }
                    function tAt(x) { return scrollSec + x / pxPerSec }
                    //! NOTE: 时间线 x 对应的是「绝对时间」；乐谱本地播放时间 = 绝对时间 - scoreOffset。
                    //! 点击落点要换算成乐谱时间再 seek，否则乐谱轨被拖动后，播放头会落在点击点之后。
                    function seekToX(x) { audioModel.seek(Math.max(0, tAt(x) - audioModel.scoreOffset)) }
                    //! NOTE: 触控板双指左右滑动 / 鼠标横向滚轮，横向滚动整条音轨。
                    function scrollByWheel(wheel) {
                        var dx = 0.0
                        if (Math.abs(wheel.pixelDelta.x) >= 1.0) {
                            dx = wheel.pixelDelta.x
                        } else if (Math.abs(wheel.angleDelta.x) >= 1.0) {
                            dx = wheel.angleDelta.x / 120.0 * 80.0
                        } else {
                            return false
                        }
                        var dSec = dx / pxPerSec
                        scrollSec = Math.max(0.0, Math.min(maxScroll, scrollSec - dSec))
                        return true
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onPressed: function(mouse) { timeline.seekToX(mouse.x) }
                        onPositionChanged: function(mouse) { if (pressed) { timeline.seekToX(mouse.x) } }
                        onWheel: function(wheel) { wheel.accepted = timeline.scrollByWheel(wheel) }
                    }

                    Canvas {
                        id: rulerCanvas
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 22
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var range = visibleDuration
                            var pxPerSec = timeline.pxPerSec
                            var minorStep = root.niceStep(8 / Math.max(0.001, pxPerSec))
                            var majorStep = root.niceStep(64 / Math.max(0.001, pxPerSec))
                            if (majorStep < minorStep) {
                                majorStep = minorStep
                            }
                            ctx.strokeStyle = "#9BA39D"
                            ctx.fillStyle = "#9BA39D"
                            ctx.font = "9px sans-serif"
                            var firstMinor = Math.ceil(scrollSec / minorStep) * minorStep
                            for (var ms = firstMinor; ms <= scrollSec + range; ms += minorStep) {
                                var mx = timeline.xAt(ms)
                                ctx.beginPath()
                                ctx.moveTo(mx, height - 4)
                                ctx.lineTo(mx, height)
                                ctx.stroke()
                            }
                            var first = Math.ceil(scrollSec / majorStep) * majorStep
                            for (var s = first; s <= scrollSec + range; s += majorStep) {
                                var x = timeline.xAt(s)
                                ctx.beginPath()
                                ctx.moveTo(x, height - 8)
                                ctx.lineTo(x, height)
                                ctx.stroke()
                                ctx.fillText(root.formatTime(s), x + 2, height - 9)
                            }
                        }
                    }

                    Rectangle {
                        id: scoreTrack
                        anchors.top: rulerCanvas.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: (parent.height - rulerCanvas.height) / 2
                        color: "transparent"

                        Canvas {
                            id: scoreGridCanvas
                            anchors.fill: parent
                            //! 【固定不变式 · 永不可改】
                            //! 乐谱轨的每一条竖线 = 对应小节的第一拍（强拍）。
                            //! 无论是否导入音频、无论轨道如何缩放/拖动，竖线都必须与播放头完全同步。
                            //! 竖线 x 时间 == 该小节第一拍的实际播放时间（含重复展开 + 速度）。
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.clearRect(0, 0, width, height)
                                var grid = audioModel.scoreBeatGrid
                                for (var i = 0; i < grid.length; ++i) {
                                    var item = grid[i]
                                    if (!item.isDownbeat) {
                                        continue
                                    }
                                    var x = timeline.xAt(item.time + audioModel.scoreOffset)
                                    if (x < -1 || x > width + 1) {
                                        continue
                                    }
                                    ctx.strokeStyle = root.scoreColor
                                    ctx.lineWidth = 3
                                    ctx.beginPath()
                                    ctx.moveTo(x, 0)
                                    ctx.lineTo(x, height)
                                    ctx.stroke()
                                }
                                ctx.lineWidth = 1
                            }
                        }

                        Connections {
                            target: audioModel
                            function onScoreBeatGridChanged() { scoreGridCanvas.requestPaint() }
                            function onScoreDurationChanged() { scoreGridCanvas.requestPaint() }
                            function onScoreOffsetChanged() { scoreGridCanvas.requestPaint() }
                        }

                        // 乐谱轨整段左右拖动
                        Rectangle {
                            id: scoreBlock
                            x: timeline.xAt(audioModel.scoreOffset)
                            y: 4
                            width: Math.max(20, timeline.pxPerSec * Math.max(1, audioModel.scoreDuration))
                            height: parent.height - 8
                            color: "transparent"

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.OpenHandCursor
                                property double pressX: 0
                                property bool moved: false
                                onPressed: function(mouse) { pressX = mouse.x; moved = false }
                                onPositionChanged: function(mouse) {
                                    if (pressed) {
                                        var dx = mouse.x - pressX
                                        if (Math.abs(dx) > 3) {
                                            moved = true
                                        }
                                        if (moved) {
                                            var d = dx / timeline.pxPerSec
                                            audioModel.setScoreOffset(Math.max(0, audioModel.scoreOffset + d))
                                        }
                                    }
                                }
                                onReleased: {
                                    if (moved) {
                                        audioModel.apply()
                                    }
                                }
                                onClicked: function(mouse) {
                                    if (!moved) {
                                        var pos = mapToItem(timeline, mouse.x, mouse.y)
                                        timeline.seekToX(pos.x)
                                    }
                                }
                                onWheel: function(wheel) { wheel.accepted = timeline.scrollByWheel(wheel) }
                            }
                        }
                    }

                    Rectangle {
                        id: audioTrack
                        anchors.top: scoreTrack.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        color: "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "导入音频文件，与乐谱对齐"
                            color: "#9BA39D"
                            visible: !audioModel.hasTrack
                        }

                        Canvas {
                            id: waveCanvas
                            anchors.fill: parent
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.clearRect(0, 0, width, height)
                                if (!audioModel.hasTrack) {
                                    return
                                }
                                var dur = audioModel.duration > 0 ? audioModel.duration : 1
                                var cs = Math.max(0, audioModel.clipStart)
                                var ce = audioModel.clipEnd > 0 ? audioModel.clipEnd : dur
                                if (ce < cs) {
                                    ce = cs
                                }
                                var clipLen = ce - cs
                                var x0 = timeline.xAt(audioModel.startOffset)
                                var x1 = timeline.xAt(audioModel.startOffset + clipLen)
                                var mid = height / 2
                                var peaks = audioModel.waveformPeaks
                                if (peaks && peaks.length > 0) {
                                    var n = peaks.length
                                    var halfH = height / 2 - 4
                                    for (var i = 0; i < n; ++i) {
                                        var t = i / n * dur
                                        var inClip = (t >= cs && t <= ce)
                                        if (!inClip) {
                                            continue
                                        }
                                        var x = timeline.xAt(audioModel.startOffset + (t - cs))
                                        var bw = Math.max(1, timeline.pxPerSec * (dur / n))
                                        var item = peaks[i]
                                        var minV = item.min
                                        var maxV = item.max
                                        var y1 = mid - maxV * halfH
                                        var y2 = mid - minV * halfH
                                        if (y2 < y1) {
                                            var tmpY = y1
                                            y1 = y2
                                            y2 = tmpY
                                        }
                                        ctx.fillStyle = root.audioColor
                                        ctx.fillRect(x, y1, bw, Math.max(1, y2 - y1))
                                    }
                                } else {
                                    ctx.fillStyle = root.audioColor
                                    ctx.fillRect(x0, mid - 1, Math.max(0, x1 - x0), 2)
                                }
                            }
                        }

                        Connections {
                            target: audioModel
                            function onWaveformPeaksChanged() { waveCanvas.requestPaint() }
                            function onDurationChanged() { waveCanvas.requestPaint() }
                            function onStartOffsetChanged() { waveCanvas.requestPaint() }
                            function onClipStartChanged() { waveCanvas.requestPaint() }
                            function onClipEndChanged() { waveCanvas.requestPaint() }
                        }

                        // 整段拖动（对齐）
                        Rectangle {
                            id: clipBody
                            x: timeline.xAt(audioModel.startOffset)
                            y: 6
                            width: Math.max(20, timeline.pxPerSec * ((audioModel.clipEnd > 0 ? audioModel.clipEnd : audioDuration) - Math.max(0, audioModel.clipStart)))
                            height: parent.height - 12
                            color: "transparent"
                            visible: audioModel.hasTrack

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.OpenHandCursor
                                property double pressX: 0
                                property bool moved: false
                                onPressed: function(mouse) { pressX = mouse.x; moved = false }
                                onPositionChanged: function(mouse) {
                                    if (pressed) {
                                        var dx = mouse.x - pressX
                                        if (Math.abs(dx) > 3) {
                                            moved = true
                                        }
                                        if (moved) {
                                            var d = dx / timeline.pxPerSec
                                            audioModel.setStartOffset(Math.max(0, audioModel.startOffset + d))
                                        }
                                    }
                                }
                                onReleased: {
                                    if (moved) {
                                        audioModel.apply()
                                    }
                                }
                                onClicked: function(mouse) {
                                    if (!moved) {
                                        var pos = mapToItem(timeline, mouse.x, mouse.y)
                                        timeline.seekToX(pos.x)
                                    }
                                }
                                onWheel: function(wheel) { wheel.accepted = timeline.scrollByWheel(wheel) }
                            }
                        }

                        // 裁剪开头把手
                        Rectangle {
                            id: leftTrim
                            x: timeline.xAt(audioModel.startOffset)
                            y: 6
                            width: 8
                            height: parent.height - 12
                            color: root.audioColor
                            visible: audioModel.hasTrack

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.SplitHCursor
                                property double startClip: 0
                                property double startOff: 0
                                onPressed: function(mouse) {
                                    startClip = Math.max(0, audioModel.clipStart)
                                    startOff = Math.max(0, audioModel.startOffset)
                                }
                                onPositionChanged: function(mouse) {
                                    if (pressed) {
                                        var d = mouse.x / timeline.pxPerSec
                                        audioModel.setClipStart(Math.max(0, startClip + d))
                                        audioModel.setStartOffset(Math.max(0, startOff + d))
                                    }
                                }
                                onReleased: audioModel.apply()
                                onWheel: function(wheel) { wheel.accepted = timeline.scrollByWheel(wheel) }
                            }
                        }

                        // 裁剪结尾把手
                        Rectangle {
                            id: rightTrim
                            x: timeline.xAt(audioModel.startOffset + ((audioModel.clipEnd > 0 ? audioModel.clipEnd : audioDuration) - Math.max(0, audioModel.clipStart)))
                            y: 6
                            width: 8
                            height: parent.height - 12
                            color: root.audioColor
                            visible: audioModel.hasTrack

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.SplitHCursor
                                property double startEnd: 0
                                onPressed: function(mouse) {
                                    startEnd = audioModel.clipEnd > 0 ? audioModel.clipEnd : audioDuration
                                }
                                onPositionChanged: function(mouse) {
                                    if (pressed) {
                                        var d = mouse.x / timeline.pxPerSec
                                        audioModel.setClipEnd(Math.max(0, startEnd + d))
                                    }
                                }
                                onReleased: audioModel.apply()
                                onWheel: function(wheel) { wheel.accepted = timeline.scrollByWheel(wheel) }
                            }
                        }
                    }

                    Rectangle {
                        id: playhead
                        x: timeline.xAt(audioModel.playbackPosition + audioModel.scoreOffset) - width / 2
                        width: Math.max(1, root.playheadThickness)
                        height: timeline.height
                        y: 0
                        color: root.playheadColor
                        visible: audioModel.playbackPosition >= 0
                    }
                }
            }
        }

        Item {
            id: scrollBar
            Layout.fillWidth: true
            Layout.preferredHeight: 14

            //! NOTE: 横条宽度 = 可视窗口占总时长的比例，与轨道缩放联动。
            //! 全部装下时铺满整条；缩放越大（看得越少）横条越短。
            property double ratio: Math.min(1.0, Math.max(0.0, visibleDuration / totalDuration))
            property double minBarWidth: Math.min(24.0, width)
            property double barWidth: ratio >= 1.0 ? width : Math.max(minBarWidth, width * ratio)
            property double travel: Math.max(0.0, width - barWidth)
            property double barX: maxScroll > 0.0
                                  ? (Math.max(0.0, Math.min(maxScroll, scrollSec)) / maxScroll) * travel
                                  : 0.0

            // 滑轨底槽
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: 4
                radius: 2
                color: "#E0E5E2"
            }

            // 点击底槽空白处：跳到点击位置（与之前 Slider 行为一致）
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor

                function jumpTo(x) {
                    if (scrollBar.travel <= 0) {
                        return
                    }
                    var t = Math.max(0.0, Math.min(scrollBar.travel, x - scrollBar.barWidth / 2))
                    scrollSec = (t / scrollBar.travel) * maxScroll
                }

                onPressed: function(mouse) { jumpTo(mouse.x) }
                onPositionChanged: function(mouse) { if (pressed) { jumpTo(mouse.x) } }
            }

            // 可短可长的横条
            Rectangle {
                id: scrollThumb
                x: scrollBar.barX
                anchors.verticalCenter: parent.verticalCenter
                width: scrollBar.barWidth
                height: 12
                radius: 6
                color: "#8B9A92"

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.OpenHandCursor
                    property double dragStartX: 0
                    property double dragStartScroll: 0

                    onPressed: function(mouse) {
                        dragStartX = mouse.x
                        dragStartScroll = scrollSec
                    }
                    onPositionChanged: function(mouse) {
                        if (pressed && scrollBar.travel > 0) {
                            var dx = mouse.x - dragStartX
                            var dSec = (dx / scrollBar.travel) * maxScroll
                            scrollSec = Math.max(0.0, Math.min(maxScroll, dragStartScroll + dSec))
                        }
                    }
                }
            }
        }
    }
}
