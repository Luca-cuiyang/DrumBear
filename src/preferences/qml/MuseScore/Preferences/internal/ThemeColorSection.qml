/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * DB Score - 主题颜色（一键换肤）
 */
import QtQuick

import Muse.Ui
import Muse.UiComponents

BaseSection {
    id: root

    title: qsTrc("preferences", "主题颜色")

    property var skins: [
        { name: qsTrc("preferences", "活力橙 · 深蓝"), accent: "#EA580C", background: "#0F1C33", theme: "dark" },
        { name: qsTrc("preferences", "天空蓝 · 冰白"), accent: "#0284C7", background: "#F5F8FC", theme: "light" },
        { name: qsTrc("preferences", "音乐紫 · 电光青"), accent: "#7C3AED", background: "#0E2A33", theme: "dark" },
        { name: qsTrc("preferences", "专业青绿 · 石墨黑"), accent: "#0D9488", background: "#181A1D", theme: "dark" }
    ]

    signal skinSelected(var skin)

    Grid {
        width: parent.width
        columns: 2
        spacing: 12

        Repeater {
            model: root.skins

            delegate: Rectangle {
                id: skinCard

                required property var modelData

                width: 200
                height: 96
                radius: 8
                color: ui.theme.backgroundSecondaryColor
                border.color: ui.theme.strokeColor
                border.width: 1

                Column {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 10

                    // 双色预览：左半强调色，右半背景色
                    Rectangle {
                        width: parent.width
                        height: 38
                        radius: 6
                        clip: true

                        Rectangle {
                            width: parent.width / 2
                            height: parent.height
                            color: skinCard.modelData.accent
                        }
                        Rectangle {
                            x: parent.width / 2
                            width: parent.width / 2
                            height: parent.height
                            color: skinCard.modelData.background
                        }
                    }

                    StyledTextLabel {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: skinCard.modelData.name
                        font: ui.theme.bodyFont
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.skinSelected(skinCard.modelData)
                }
            }
        }
    }
}
