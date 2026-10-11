/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2021 MuseScore Limited and others
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

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Dock
import Muse.Interactive
import Muse.Ui
import Muse.UiComponents
import Muse.Cloud
import DBScore.AppShell

import "./HomePage"
import "./NotationPage"
import "./NotationReviewPage"
import "./DevTools"
import "./AccountPage"

DockWindow {
    id: root

    objectName: "WindowContent"

    property int sendCooldown: 0

    DbScoreAccountModel {
        id: accountModel
    }

    Timer {
        id: cooldownTimer
        interval: 1000
        repeat: true
        running: root.sendCooldown > 0
        onTriggered: {
            if (root.sendCooldown > 0) {
                root.sendCooldown -= 1
            }
        }
    }

    onPageLoaded: {
        console.log("WindowContent::onPageLoaded")
        interactiveProvider.onPageOpened()
    }

    InteractiveProvider {
        id: interactiveProvider
        topParent: root

        onRequestedDockPage: function(uri, params) {
            root.loadPage(uri, params)
        }
    }

    NavigationSection {
        id: topToolbarKeyNavSec
        name: "TopTool"
        order: 1
    }

    toolBars: [
        DockToolBar {
            id: mainToolBar

            objectName: "mainToolBar"
            title: qsTrc("appshell", "Main toolbar")

            floatable: false
            closable: false

            navigationSection: topToolbarKeyNavSec

            MainToolBar {
                id: toolBar
                navigation.section: mainToolBar.navigationSection
                navigation.order: 1

                currentUri: root.currentPageUri

                navigation.onActiveChanged: {
                    if (navigation.active) {
                        mainToolBar.forceActiveFocus()
                    }
                }

                onSelected: function(uri) {
                    root.openPage(uri)
                }

                Component.onCompleted: {
                    toolBar.focusOnFirst()
                }
            }
        }
    ]

    pages: [
        HomePage {
            window: root.window
        },

        NotationPage {
            topToolbarKeyNavSec: topToolbarKeyNavSec
        },

        NotationReviewPage {
            topToolbarKeyNavSec: topToolbarKeyNavSec
        },

        DevToolsPage {},

        AccountPage {}
    ]

    // 登录墙：未登录时覆盖整个窗口，必须先登录/注册
    Rectangle {
        visible: !accountModel.phoneLoggedIn
        anchors.fill: parent
        z: 1000
        color: ui.theme.backgroundPrimaryColor

        Rectangle {
            width: 420
            height: 320
            anchors.centerIn: parent
            radius: 16
            color: ui.theme.backgroundSecondaryColor

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 32
                spacing: 14

                StyledTextLabel {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTrc("appshell", "登录 / 注册")
                    font: ui.theme.titleBoldFont
                }

                StyledTextLabel {
                    Layout.fillWidth: true
                    text: qsTrc("appshell", "登录后获得 3 天免费试用，未注册手机号将自动注册")
                    font: ui.theme.bodyFont
                    opacity: 0.7
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    StyledTextLabel {
                        text: qsTrc("appshell", "手机号")
                        font: ui.theme.bodyFont
                    }
                    TextField {
                        id: loginPhoneField
                        Layout.fillWidth: true
                        placeholderText: qsTrc("appshell", "请输入手机号")
                        inputMethodHints: Qt.ImhDigitsOnly
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    StyledTextLabel {
                        text: qsTrc("appshell", "验证码")
                        font: ui.theme.bodyFont
                    }
                    TextField {
                        id: loginCodeField
                        Layout.fillWidth: true
                        placeholderText: qsTrc("appshell", "6位验证码")
                        inputMethodHints: Qt.ImhDigitsOnly
                    }
                    FlatButton {
                        text: root.sendCooldown > 0
                              ? (root.sendCooldown + qsTrc("appshell", "s 后重发"))
                              : qsTrc("appshell", "获取验证码")
                        enabled: !accountModel.busy && root.sendCooldown === 0
                        onClicked: {
                            accountModel.sendCode(loginPhoneField.text)
                            root.sendCooldown = 60
                        }
                    }
                }

                StyledTextLabel {
                    visible: accountModel.lastError.length > 0
                    Layout.fillWidth: true
                    text: accountModel.lastError
                    color: ui.theme.accentColor
                    font: ui.theme.bodyFont
                    wrapMode: Text.WordWrap
                }

                FlatButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    text: qsTrc("appshell", "登录 / 注册")
                    accentButton: true
                    enabled: !accountModel.busy
                    onClicked: accountModel.loginByPhone(loginPhoneField.text, loginCodeField.text)
                }
            }
        }
    }
}
