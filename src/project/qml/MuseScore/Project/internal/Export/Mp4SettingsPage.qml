/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2025 MuseScore Limited
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

import Muse.UiComponents
import Muse.Ui
import DBScore.Project

ExportSettingsPage {
    id: root

    property bool isFFmpegAvailable: Boolean(root.model) && root.model.isFFmpegAvailable
    readonly property bool mp4ExportLocked: Boolean(root.model) && root.model.mp4ExportLocked

    isExportAvailable: root.isFFmpegAvailable && !root.mp4ExportLocked

    Loader {
        width: parent.width

        sourceComponent: root.mp4ExportLocked ? lockedComp
                         : root.isFFmpegAvailable ? videoSettingsComp
                         : ffmpegMissingComp
    }

    Component {
        id: lockedComp

        Column {
            width: parent.width
            spacing: 16

            StyledTextLabel {
                width: parent.width
                text: qsTrc("project/export", "导出 MP4 视频需要开通会员")
                font: ui.theme.bodyBoldFont
                horizontalAlignment: Text.AlignHCenter
            }

            StyledTextLabel {
                width: parent.width
                text: qsTrc("project/export", "免费试用与已到期会员不支持导出 MP4 视频。开通年度会员后即可导出动态乐谱视频。")
                horizontalAlignment: Text.AlignLeft
                wrapMode: Text.WordWrap
            }

            FlatButton {
                width: parent.width
                text: qsTrc("project/export", "开通会员")
                accentButton: true

                navigation.name: "ExportOpenMembership"
                navigation.panel: root.navigationPanel
                navigation.row: root.navigationOrder

                onClicked: {
                    if (root.model) {
                        root.model.openMembershipPage()
                    }
                }
            }
        }
    }

    Component {
        id: ffmpegMissingComp

        Column {
            width: parent.width
            spacing: 12

            StyledTextLabel {
                width: parent.width
                text: qsTrc("project/export", "To export to this file format, an FFmpeg installation is required. You can also configure this in Preferences > Video.")
                horizontalAlignment: Text.AlignLeft
                wrapMode: Text.WordWrap
            }

            FlatButton {
                id: downloadButton

                text: qsTrc("project/export", "Download FFmpeg")
                icon: IconCode.OPEN_LINK
                isNarrow: true
                orientation: Qt.Horizontal

                navigation.name: "ExportDownloadFFmpeg"
                navigation.panel: root.navigationPanel
                navigation.row: root.navigationOrder

                onClicked: {
                    api.launcher.openUrl("https://handbook.drumbearai.com/video/installing-ffmpeg")
                }
            }

            FilePicker {
                width: parent.width

                pickerType: FilePicker.PickerType.Directory
                dialogTitle: qsTrc("project/export", "Choose FFmpeg library folder")

                buttonType: FlatButton.TextOnly
                buttonText: qsTrc("project/export", "Locate existing installation")
                showPathField: false

                dir: root.model ? root.model.ffmpegDir : ""
                path: root.model ? root.model.ffmpegDir : ""

                navigation: root.navigationPanel
                navigationRowOrderStart: downloadButton.navigation.order + 1

                onPathEdited: function(newPath) {
                    if (root.model) {
                        root.model.ffmpegDir = newPath
                    }
                }
            }
        }
    }

    Component {
        id: videoSettingsComp

        Column {
            width: parent.width
            spacing: 12

            AudioSettings {
                id: audioSection

                model: root.model
                navigationPanel: root.navigationPanel
                navigationOrderStart: root.navigationOrder
                showBitRateControl: true
            }

            ExportOptionItem {
                id: videoResolutionLabel
                text: qsTrc("project/export", "视频分辨率")

                StyledDropdown {
                    id: videoResolutionDropdown
                    Layout.preferredWidth: 260

                    navigation.name: "VideoResolutionDropdown"
                    navigation.panel: root.navigationPanel
                    navigation.row: audioSection.navigationOrderEnd + 1
                    navigation.accessible.name: videoResolutionLabel.text + " " + currentText

                    model: root.model ? root.model.availableVideoResolutions() : []

                    currentIndex: root.model ? indexOfValue(root.model.videoResolution) : -1

                    onActivated: function(index, value) {
                        root.model.videoResolution = value
                    }
                }
            }

            ExportOptionItem {
                id: videoFpsLabel
                text: qsTrc("project/export", "帧率")

                StyledDropdown {
                    id: videoFpsDropdown
                    Layout.preferredWidth: 200

                    navigation.name: "VideoFpsDropdown"
                    navigation.panel: root.navigationPanel
                    navigation.row: audioSection.navigationOrderEnd + 2
                    navigation.accessible.name: videoFpsLabel.text + " " + currentText

                    model: root.model ? root.model.availableVideoFps().map(function(obj) {
                        return { text: obj.text, value: obj.value }
                    }) : []

                    currentIndex: root.model ? indexOfValue(root.model.videoFps) : -1

                    onActivated: function(index, value) {
                        root.model.videoFps = value
                    }
                }
            }

            StyledTextLabel {
                width: parent.width
                text: qsTrc("project/export", "提示：帧率越高文件越大、导出越慢。120/240 帧文件较大，部分播放器可能无法流畅播放。")
                horizontalAlignment: Text.AlignLeft
                wrapMode: Text.WordWrap
                opacity: 0.7
            }

            RadioButtonGroup {
                orientation: ListView.Vertical
                spacing: 8
                width: parent.width

                model: root.model ? root.model.availableViewModes().map(function(obj) {
                    return { text: obj.text, value: obj.value }
                }) : []

                delegate: RoundedRadioButton {
                    required property var modelData
                    required property int index

                    text: modelData.text
                    checked: root.model.viewMode === modelData.value
                    onToggled: root.model.viewMode = modelData.value

                    navigation.name: modelData.text
                    navigation.panel: root.navigationPanel
                    navigation.row: videoResolutionDropdown.navigation.row + 1 + index
                    navigation.accessible.name: modelData.text
                }
            }

            CheckBox {
                width: parent.width
                text: qsTrc("project/export", "开启跨页垂直滑动")

                navigation.name: "SmoothPageTransitionsCheckbox"
                navigation.panel: root.navigationPanel
                navigation.row: videoResolutionDropdown.navigation.row + 4

                checked: root.model ? root.model.smoothPageTransitions : false
                onClicked: {
                    if (root.model) {
                        root.model.smoothPageTransitions = !checked
                    }
                }
            }

            CheckBox {
                width: parent.width
                text: qsTrc("project/export", "导出时包含伴奏音频")

                navigation.name: "IncludeAccompanimentAudioCheckbox"
                navigation.panel: root.navigationPanel
                navigation.row: videoResolutionDropdown.navigation.row + 5

                checked: root.model ? root.model.includeAccompanimentAudio : true
                onClicked: {
                    if (root.model) {
                        root.model.includeAccompanimentAudio = !checked
                    }
                }
            }

            StyledTextLabel {
                width: parent.width
                text: qsTrc("project/export", "Each selected part will be exported as a separate video file.")
                horizontalAlignment: Text.AlignLeft
                wrapMode: Text.WordWrap
            }
        }
    }
}
