/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) MuseScore Limited and others
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

#include "playbackcommandsregister.h"

#include "../playbackcommands.h"

using namespace muse;
using namespace muse::rcommand;
using namespace muse::ui;
using namespace mu::playback;

static const std::vector<CommandInfo> s_commandInfos = {
    CommandInfo{
        PLAY_TOGGLE_COMMAND,
        TranslatableString("playback", "播放/暂停"),
        TranslatableString("playback", "播放或暂停当前乐谱"),
        InputSchema(),
        Decoration(IconCode::Code::PLAY)
    },
    CommandInfo{
        PLAY_COMMAND,
        TranslatableString("playback", "播放"),
        TranslatableString("playback", "播放当前乐谱"),
        InputSchema(),
        Decoration(IconCode::Code::PLAY)
    },
    CommandInfo{
        PLAY_SELECTION_COMMAND,
        TranslatableString("playback", "从选段播放"),
        TranslatableString("playback", "从选段播放"),
        InputSchema(),
        Decoration(IconCode::Code::PLAY)
    },
    CommandInfo{
        PAUSE_COMMAND,
        TranslatableString("playback", "暂停"),
        TranslatableString("playback", "暂停播放"),
        InputSchema(),
        Decoration(IconCode::Code::PAUSE)
    },
    CommandInfo{
        PAUSE_AND_SELECT_COMMAND,
        TranslatableString("playback", "暂停并选择"),
        TranslatableString("playback", "暂停并选择播放位置"),
        InputSchema(),
        Decoration(IconCode::Code::PAUSE)
    },
    CommandInfo{
        STOP_COMMAND,
        TranslatableString("playback", "停止"),
        TranslatableString("playback", "停止播放"),
        InputSchema(),
        Decoration(IconCode::Code::STOP)
    },
    CommandInfo{
        REWIND_COMMAND,
        TranslatableString("playback", "回退"),
        TranslatableString("playback", "回退"),
        InputSchema({ { "position", Arg(DataType::Float, u"播放位置（秒）", Val(0)) } }),
        Decoration(IconCode::Code::REWIND)
    },
    CommandInfo{
        LOOP_TOGGLE_COMMAND,
        TranslatableString("playback", "循环播放"),
        TranslatableString("playback", "开启或关闭循环播放"),
        InputSchema(),
        Decoration(IconCode::Code::LOOP, rcommand::Checkable::Yes)
    },

    CommandInfo{
        LOOP_IN_COMMAND,
        TranslatableString("playback", "循环起点"),
        TranslatableString("playback", "设置循环左标记"),
        InputSchema(),
        Decoration(IconCode::Code::LOOP_IN)
    },
    CommandInfo{
        LOOP_OUT_COMMAND,
        TranslatableString("playback", "循环终点"),
        TranslatableString("playback", "设置循环右标记"),
        InputSchema(),
        Decoration(IconCode::Code::LOOP_OUT)
    },
    CommandInfo{
        METRONOME_TOGGLE_COMMAND,
        TranslatableString("playback", "节拍器"),
        TranslatableString("playback", "开启或关闭节拍器"),
        InputSchema(),
        Decoration(IconCode::Code::METRONOME, rcommand::Checkable::Yes)
    },
    CommandInfo{
        OPEN_PLAYBACK_SETUP_COMMAND,
        TranslatableString("playback", "播放设置"),
        TranslatableString("playback", "显示播放设置"),
        InputSchema(),
        Decoration(IconCode::Code::NONE)
    },
    CommandInfo{
        MIDI_TOGGLE_COMMAND,
        TranslatableString("playback", "MIDI 输入"),
        TranslatableString("playback", "开启或关闭 MIDI 输入"),
        InputSchema(),
        Decoration(IconCode::Code::MIDI_INPUT, rcommand::Checkable::Yes)
    },
    CommandInfo{
        MIDI_INPUT_WRITTEN_PITCH_COMMAND,
        TranslatableString("playback", "记谱音高"),
        TranslatableString("playback", "按记谱音高输入"),
        InputSchema(),
        Decoration(IconCode::Code::NONE, rcommand::Checkable::Yes)
    },
    CommandInfo{
        MIDI_INPUT_SOUNDING_PITCH_COMMAND,
        TranslatableString("playback", "实际音高"),
        TranslatableString("playback", "按实际音高输入"),
        InputSchema(),
        Decoration(IconCode::Code::NONE, rcommand::Checkable::Yes)
    },
    CommandInfo{
        REPEATS_TOGGLE_COMMAND,
        TranslatableString("playback", "播放反复"),
        TranslatableString("playback", "开启或关闭播放反复"),
        InputSchema(),
        Decoration(IconCode::Code::PLAY_REPEATS, rcommand::Checkable::Yes)
    },
    CommandInfo{
        CHORDSYMBOLS_TOGGLE_COMMAND,
        TranslatableString("playback", "播放和弦符号"),
        TranslatableString("playback", "开启或关闭播放和弦符号"),
        InputSchema(),
        Decoration(IconCode::Code::CHORD_SYMBOL, rcommand::Checkable::Yes)
    },
    CommandInfo{
        HEAR_PLAYBACK_WHEN_EDITING_TOGGLE_COMMAND,
        TranslatableString("playback", "编辑时试听"),
        TranslatableString("playback", "开启或关闭编辑时试听"),
        InputSchema(),
        Decoration(IconCode::Code::AUDIO, rcommand::Checkable::Yes)
    },
    CommandInfo{
        PAN_TOGGLE_COMMAND,
        TranslatableString("playback", "播放时自动平移乐谱"),
        TranslatableString("playback", "开启或关闭播放时自动平移乐谱"),
        InputSchema(),
        Decoration(IconCode::Code::PAN_SCORE, rcommand::Checkable::Yes)
    },
    CommandInfo{
        COUNTIN_TOGGLE_COMMAND,
        TranslatableString("playback", "播放前数拍"),
        TranslatableString("playback", "开启或关闭播放前数拍"),
        InputSchema(),
        Decoration(IconCode::Code::COUNT_IN, rcommand::Checkable::Yes)
    },
    CommandInfo{
        CLEAR_ONLINESOUNDS_CACHE_COMMAND,
        TranslatableString("playback", "清除在线音色缓存"),
        TranslatableString("playback", "清除在线音色缓存"),
        InputSchema(),
        Decoration(IconCode::Code::NONE)
    },
    CommandInfo{
        PROCESS_ONLINESOUNDS_COMMAND,
        TranslatableString("playback", "处理在线音色"),
        TranslatableString("playback", "处理在线音色"),
        InputSchema(),
        Decoration(IconCode::Code::NONE)
    },
    CommandInfo{
        RELOAD_PLAYBACK_CACHE_COMMAND,
        TranslatableString("playback", "重新加载播放缓存"),
        TranslatableString("playback", "重新加载播放缓存"),
        InputSchema(),
        Decoration(IconCode::Code::NONE)
    },

    CommandInfo{
        TOGGLE_MIXER_SECTION_COMMAND,
        TranslatableString("playback", "切换混音器分区"),
        TranslatableString("playback", "切换混音器分区"),
        InputSchema({
            { "section",
              Arg(DataType::String, u"混音器分区（标签、音色、音频效果、声像、音量、推子、静音与独奏、标题）") } }),
        Decoration()
    },
    CommandInfo{
        TOGGLE_AUX_SEND_COMMAND,
        TranslatableString("playback", "切换辅助发送"),
        TranslatableString("playback", "切换辅助发送"),
        InputSchema({ { "auxsend-index", Arg(DataType::Integer, u"辅助发送索引") } }),
        Decoration()
    },
    CommandInfo{
        TOGGLE_AUX_CHANNEL_COMMAND,
        TranslatableString("playback", "切换辅助通道"),
        TranslatableString("playback", "切换辅助通道"),
        InputSchema({ { "auxchannel-index", Arg(DataType::Integer, u"辅助通道索引") } }),
        Decoration()
    }
};

std::string PlaybackCommandsRegister::moduleName() const
{
    return "playback";
}

const std::vector<muse::rcommand::Command>& PlaybackCommandsRegister::commandList() const
{
    static std::vector<muse::rcommand::Command> commands;
    if (commands.empty()) {
        commands.reserve(s_commandInfos.size());
        for (const auto& info : s_commandInfos) {
            commands.push_back(info.command);
        }
    }
    return commands;
}

const std::vector<CommandInfo>& PlaybackCommandsRegister::commandInfoList() const
{
    return s_commandInfos;
}
