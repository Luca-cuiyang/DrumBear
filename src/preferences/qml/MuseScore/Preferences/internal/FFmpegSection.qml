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

BaseSection {
    id: root

    title: qsTrc("preferences", "视频导出组件")

    property var model: null

    ColumnLayout {
        width: parent.width
        height: 30

        spacing: 12

        StyledTextLabel {
            id: titleLabel
            Layout.fillWidth: true
            text: model && model.ffmpegVersion !== -1
                  ? qsTrc("preferences", "内置视频组件已就绪")
                  : qsTrc("preferences", "内置视频组件加载失败，请重新安装最新版 DB Score")
            horizontalAlignment: Text.AlignLeft
        }
    }
}
