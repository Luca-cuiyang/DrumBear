/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2026 DB Score contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */
import QtQuick
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents
import DBScore.Project

StyledDialogView {
    id: root

    contentHeight: 600
    contentWidth: 640
    margins: 20

    objectName: "AudioTrackDialog"

    AudioTrackSettingsModel {
        id: audioModel

        Component.onCompleted: {
            audioModel.load()
        }
    }

    property double timeRange: audioModel.duration > 0 ? audioModel.duration : 600

    ColumnLayout {
        id: content

        anchors.fill: parent
        spacing: 16

        StyledTextLabel {
            text: qsTrc("project", "Accompaniment track")
            font: ui.theme.largeBodyBoldFont
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            StyledTextLabel {
                Layout.fillWidth: true
                text: audioModel.hasTrack ? audioModel.filePath : qsTrc("project", "No audio track selected")
                elide: Text.ElideMiddle
                wrapMode: Text.NoWrap
            }

            FlatButton {
                text: qsTrc("project", "Choose…")

                onClicked: {
                    audioModel.chooseFile()
                }
            }

            FlatButton {
                text: qsTrc("project", "Remove")
                enabled: audioModel.hasTrack

                onClicked: {
                    audioModel.remove()
                }
            }
        }

        Canvas {
            id: waveCanvas

            Layout.fillWidth: true
            Layout.preferredHeight: 120

            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)

                var mid = height / 2
                var peaks = audioModel.waveformPeaks
                if (!peaks || peaks.length === 0) {
                    ctx.fillStyle = "#4d4d4d"
                    ctx.fillRect(0, mid - 1, width, 2)
                    return
                }

                var n = peaks.length
                var barWidth = Math.max(1, width / n)
                var clipStartFrac = audioModel.duration > 0 ? audioModel.clipStart / audioModel.duration : 0
                var clipEndFrac = audioModel.duration > 0
                                  ? (audioModel.clipEnd > 0 ? audioModel.clipEnd / audioModel.duration : 1)
                                  : 1

                for (var i = 0; i < n; ++i) {
                    var frac = i / n
                    var amp = Math.max(1, peaks[i] * mid)
                    ctx.fillStyle = (frac >= clipStartFrac && frac <= clipEndFrac) ? "#2f80ed" : "#6f6f6f"
                    ctx.fillRect(i * barWidth, mid - amp, Math.max(1, barWidth - 1), amp * 2)
                }
            }

            Connections {
                target: audioModel
                function onWaveformPeaksChanged() { waveCanvas.requestPaint() }
                function onClipStartChanged() { waveCanvas.requestPaint() }
                function onClipEndChanged() { waveCanvas.requestPaint() }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 20
            rowSpacing: 12

            StyledTextLabel { text: qsTrc("project", "Start offset") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.startOffset
                    from: 0
                    to: timeRange
                    stepSize: 0.01
                    onMoved: { audioModel.setStartOffset(value) }
                }
                StyledTextLabel { text: audioModel.startOffset.toFixed(2) + " s" }
            }

            StyledTextLabel { text: qsTrc("project", "Clip start") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.clipStart
                    from: 0
                    to: timeRange
                    stepSize: 0.01
                    onMoved: { audioModel.setClipStart(value) }
                }
                StyledTextLabel { text: audioModel.clipStart.toFixed(2) + " s" }
            }

            StyledTextLabel { text: qsTrc("project", "Clip end") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange
                    from: 0
                    to: timeRange
                    stepSize: 0.01
                    onMoved: { audioModel.setClipEnd(value) }
                }
                StyledTextLabel { text: (audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange).toFixed(2) + " s" }
            }

            StyledTextLabel { text: qsTrc("project", "Volume") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.volumeDb
                    from: -60
                    to: 12
                    stepSize: 0.5
                    onMoved: { audioModel.setVolumeDb(value) }
                }
                StyledTextLabel { text: audioModel.volumeDb.toFixed(1) + " dB" }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 24

            CheckBox {
                text: qsTrc("project", "Mute")
                checked: audioModel.muted
                onCheckedChanged: { audioModel.setMuted(checked) }
            }

            CheckBox {
                text: qsTrc("project", "Follow score tempo")
                checked: audioModel.tempoSync
                onCheckedChanged: { audioModel.setTempoSync(checked) }
            }
        }

        Item { Layout.fillHeight: true }

        SeparatorLine {
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTrc("global", "Cancel")

                onClicked: {
                    root.reject()
                }
            }

            FlatButton {
                accentButton: true
                text: qsTrc("global", "OK")

                onClicked: {
                    audioModel.apply()
                    root.ret = { "errcode": 0 }
                    root.hide()
                }
            }
        }
    }
}
