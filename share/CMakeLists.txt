# SPDX-License-Identifier: GPL-3.0-only
# MuseScore-Studio-CLA-applies
#
# MuseScore Studio
# Music Composition & Notation
#
# Copyright (C) 2021 MuseScore Limited and others
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

subdirs(testflowscripts icons templates wallpapers locale styles sound manual instruments)

install (DIRECTORY
    plugins
    DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}
    PATTERN ".*" EXCLUDE
    )

install (DIRECTORY
    ai_transcription
    DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}
    PATTERN ".*" EXCLUDE
    )

install (DIRECTORY
    ${PROJECT_SOURCE_DIR}/tools/ai_transcription/
    DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}/ai_transcription
    PATTERN ".*" EXCLUDE
    PATTERN "test_*.py" EXCLUDE
    PATTERN "__pycache__" EXCLUDE
    )

if (MUSE_AI_TRANSCRIPTION_PYTHON_DIR)
    install (DIRECTORY
        ${MUSE_AI_TRANSCRIPTION_PYTHON_DIR}/
        DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}/ai_transcription/python
        PATTERN "*.pyc" EXCLUDE
        PATTERN "__pycache__" EXCLUDE
        )
    install (CODE
        "file(CHMOD_RECURSE
            \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${MUSE_APP_INSTALL_RESOURCES_LOCATION}/ai_transcription/python\"
            PERMISSIONS
            OWNER_READ OWNER_WRITE OWNER_EXECUTE
            GROUP_READ GROUP_EXECUTE
            WORLD_READ WORLD_EXECUTE)"
        )
endif()

install (DIRECTORY
    extensions
    DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}
    PATTERN ".*" EXCLUDE
    )

install (DIRECTORY
    workspaces
    DESTINATION ${MUSE_APP_INSTALL_RESOURCES_LOCATION}
    PATTERN ".*" EXCLUDE
    )
