/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2025 MuseScore Limited and others
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
#pragma once

#include "global/async/asyncable.h"

#include "global/modularity/ioc.h"
#include "interactive/iinteractive.h"
#include "actions/iactionsdispatcher.h"
#include "context/iglobalcontext.h"
#include "audio/main/istartaudiocontroller.h"
#include "audio/main/isoundfontcontroller.h"
#include "project/inotationproject.h"
#include "project/types/projecttypes.h"

namespace mu::appjs {
class WebApi : public muse::async::Asyncable
{
    inline static muse::GlobalInject<muse::audio::IStartAudioController> startAudioController;
    inline static muse::GlobalInject<muse::audio::ISoundFontController> soundFontController;

public:

    static WebApi* instance();

    void init(const muse::modularity::ContextPtr& context);
    void deinit();

    void load(const void* source, unsigned int len);
    void addSoundFont(const std::string& uri);
    void startAudioProcessing();

private:

    WebApi() = default;

    std::shared_ptr<mu::context::IGlobalContext> globalContext() const;
    std::shared_ptr<muse::IInteractive> interactive() const;
    std::shared_ptr<muse::actions::IActionsDispatcher> dispatcher() const;

    void onProjectSaved(const muse::io::path_t& path, mu::project::SaveMode mode);

    muse::modularity::ContextPtr m_context;
    project::INotationProjectPtr m_currentProject;
};
}
