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
#include "webapi.h"

#ifdef Q_OS_WASM
#include <emscripten/bind.h>
#include <emscripten/val.h>
#endif

#include "global/io/file.h"
#include "log.h"

#include "engraving/dom/box.h"
#include "engraving/dom/masterscore.h"
#include "engraving/dom/measure.h"
#include "engraving/dom/measurebase.h"
#include "engraving/dom/score.h"
#include "engraving/style/style.h"
#include "engraving/types/spatium.h"

#include "notation/inotation.h"
#include "notation/inotationelements.h"
#include "notation/inotationpainting.h"
#include "notation/inotationundostack.h"
#include "notation/inotationviewstate.h"
#include "notation/imasternotation.h"
#include "notation/types/viewmode.h"

using namespace muse;
using namespace mu::appjs;

namespace mu::appjs::detail {
struct PlayerLayoutState {
    struct BreakState {
        engraving::MeasureBase* item = nullptr;
        bool lineBreak = false;
        bool pageBreak = false;
        bool sectionBreak = false;
        bool noBreak = false;
    };

    engraving::Score* score = nullptr;
    double pageWidth = 0.0;
    double pageHeight = 0.0;
    double pagePrintableWidth = 0.0;
    double pageEvenLeftMargin = 0.0;
    double pageOddLeftMargin = 0.0;
    double pageEvenTopMargin = 0.0;
    double pageEvenBottomMargin = 0.0;
    double pageOddTopMargin = 0.0;
    double pageOddBottomMargin = 0.0;
    double spatium = 0.0;
    double staffUpperBorder = 0.0;
    double staffLowerBorder = 0.0;
    double minSystemDistance = 0.0;
    double maxSystemDistance = 0.0;
    bool pageTwosided = false;
    bool verticalSpread = false;
    bool showUnprintable = true;
    bool showFrames = true;

    engraving::Box* titleBox = nullptr;
    double titleHeight = 0.0;
    double titleTopGap = 0.0;
    double titleBottomGap = 0.0;
    bool titleAutoSize = true;
    bool titleVisible = true;

    std::vector<BreakState> breaks;
    bool portraitApplied = false;
};
}

#ifdef Q_OS_WASM
static void callJsWithBytes(const char* fnname, const uint8_t* data, size_t size)
{
    emscripten::val jsArray = emscripten::val::global("Uint8Array").new_(
        emscripten::typed_memory_view(size, data)
        );

    emscripten::val::module_property(fnname)(jsArray);
}

#else

static void callJsWithBytes(const char*, const uint8_t*, size_t)
{
    NOT_SUPPORTED;
}

#endif

WebApi* WebApi::instance()
{
    static WebApi a;

    return &a;
}

WebApi::~WebApi() = default;

std::shared_ptr<mu::context::IGlobalContext> WebApi::globalContext() const
{
    return muse::modularity::ioc(m_context)->resolve<mu::context::IGlobalContext>("context");
}

std::shared_ptr<muse::IInteractive> WebApi::interactive() const
{
    return muse::modularity::ioc(m_context)->resolve<muse::IInteractive>("interactive");
}

std::shared_ptr<muse::actions::IActionsDispatcher> WebApi::dispatcher() const
{
    return muse::modularity::ioc(m_context)->resolve<muse::actions::IActionsDispatcher>("actions");
}

std::shared_ptr<mu::playback::IPlaybackController> WebApi::playbackController() const
{
    return muse::modularity::ioc(m_context)->resolve<mu::playback::IPlaybackController>("playback");
}

void WebApi::init(const muse::modularity::ContextPtr& context)
{
    m_context = context;
    auto appContext = globalContext();
    IF_ASSERT_FAILED(appContext) {
        return;
    }

    auto onProjectChanged = [this]() {
        if (m_currentProject) {
            m_currentProject->saveComplited().disconnect(this);
        }

        m_currentProject = globalContext()->currentProject();
        if (m_playerLayoutState
            && m_playerLayoutState->score
            != (m_currentProject && m_currentProject->masterNotation()
                ? static_cast<engraving::Score*>(m_currentProject->masterNotation()->masterScore())
                : nullptr)) {
            m_playerLayoutState.reset();
        }

        if (m_currentProject) {
            m_currentProject->saveComplited().onReceive(this, [this](const muse::io::path_t& path, project::SaveMode mode) {
                onProjectSaved(path, mode);
            });
        }
    };

    appContext->currentProjectChanged().onNotify(this, onProjectChanged);

    onProjectChanged();
}

void WebApi::deinit()
{
    if (m_currentProject) {
        m_currentProject->saveComplited().disconnect(this);
    }
}

void WebApi::load(const void* source, unsigned int len)
{
    LOGI() << source << ", len: " << len;
    ByteArray data(reinterpret_cast<const uint8_t*>(source), len);
    const io::path_t tempFilePath = "/current.mscz";

    io::File::remove(tempFilePath);

    if (!io::File::writeFile(tempFilePath, data) || !io::File::exists(tempFilePath)) {
        LOGE() << "failed write temporary score: " << tempFilePath;
        return;
    }

    dispatcher()->dispatch("file-open", actions::ActionData::make_arg1(QUrl::fromLocalFile(tempFilePath.toQString())));
}

void WebApi::addSoundFont(const std::string& uri)
{
    soundFontController()->addSoundFont(Uri(uri));
}

void WebApi::startAudioProcessing()
{
    startAudioController()->startAudioProcessing(IApplication::RunMode::GuiApp);
}

void WebApi::togglePlayback()
{
    const auto context = globalContext();
    IF_ASSERT_FAILED(context && context->playbackState()) {
        return;
    }

    const auto playback = playbackController();
    IF_ASSERT_FAILED(playback) {
        return;
    }

    if (context->playbackState()->isPlaying()) {
        playback->pause();
    } else {
        playback->play();
    }
}

int WebApi::playbackState() const
{
    int state = 0;
    const auto context = globalContext();
    const auto playback = playbackController();

    if (playback && playback->isPlaybackInited()) {
        state |= 1;
    }
    if (playback && playback->isPlayAllowed()) {
        state |= 2;
    }
    if (context && context->currentNotation()) {
        state |= 4;
    }
    if (playback && playback->isPlaying()) {
        state |= 8;
    }

    return state;
}

int WebApi::scoreRevision() const
{
    const auto context = globalContext();
    if (!context || !context->currentNotation()) {
        return -1;
    }

    const auto undoStack = context->currentNotation()->undoStack();
    if (!undoStack) {
        return -1;
    }

    return static_cast<int>(undoStack->currentStateIndex());
}

bool WebApi::setPlayerLayout(const std::string& layout, int viewportWidth, int viewportHeight)
{
    (void)viewportWidth;
    (void)viewportHeight;

    const auto context = globalContext();
    if (!context || !context->currentNotation()) {
        return false;
    }

    notation::INotationPtr notation = context->currentNotation();
    engraving::Score* score = notation->elements()->msScore();
    if (!score) {
        return false;
    }

    if (!m_playerLayoutState || m_playerLayoutState->score != score) {
        auto state = std::make_unique<detail::PlayerLayoutState>();
        state->score = score;

        const engraving::MStyle& style = score->style();
        state->pageWidth = style.styleD(engraving::Sid::pageWidth);
        state->pageHeight = style.styleD(engraving::Sid::pageHeight);
        state->pagePrintableWidth = style.styleD(engraving::Sid::pagePrintableWidth);
        state->pageEvenLeftMargin = style.styleD(engraving::Sid::pageEvenLeftMargin);
        state->pageOddLeftMargin = style.styleD(engraving::Sid::pageOddLeftMargin);
        state->pageEvenTopMargin = style.styleD(engraving::Sid::pageEvenTopMargin);
        state->pageEvenBottomMargin = style.styleD(engraving::Sid::pageEvenBottomMargin);
        state->pageOddTopMargin = style.styleD(engraving::Sid::pageOddTopMargin);
        state->pageOddBottomMargin = style.styleD(engraving::Sid::pageOddBottomMargin);
        state->spatium = style.styleD(engraving::Sid::spatium);
        state->staffUpperBorder = style.styleAbsolute(engraving::Sid::staffUpperBorder);
        state->staffLowerBorder = style.styleAbsolute(engraving::Sid::staffLowerBorder);
        state->minSystemDistance = style.styleAbsolute(engraving::Sid::minSystemDistance);
        state->maxSystemDistance = style.styleAbsolute(engraving::Sid::maxSystemDistance);
        state->pageTwosided = style.styleB(engraving::Sid::pageTwosided);
        state->verticalSpread = style.styleB(engraving::Sid::enableVerticalSpread);
        state->showUnprintable = score->showUnprintable();
        state->showFrames = score->showFrames();

        if (score->first() && score->first()->isVBox()) {
            state->titleBox = static_cast<engraving::Box*>(score->first());
            state->titleHeight = state->titleBox->boxHeight().val();
            state->titleTopGap = state->titleBox->topGap().val();
            state->titleBottomGap = state->titleBox->bottomGap().val();
            state->titleAutoSize = state->titleBox->isAutoSizeEnabled();
            state->titleVisible = state->titleBox->visible();
        }

        for (engraving::MeasureBase* item = score->first(); item; item = item->next()) {
            state->breaks.push_back({ item, item->lineBreak(), item->pageBreak(), item->sectionBreak(),
                                      item->noBreak() });
        }

        m_playerLayoutState = std::move(state);
    }

    detail::PlayerLayoutState& state = *m_playerLayoutState;
    const bool portrait = layout == "portrait";
    bool changed = false;
    if (portrait && !state.portraitApplied) {
        engraving::MStyle& style = score->style();
        constexpr double MM_TO_INCH = 1.0 / 25.4;
        const double pageWidthMm = 50.8;
        constexpr double aspect = 844.0 / 390.0;
        const double pageHeightMm = pageWidthMm * aspect;

        style.set(engraving::Sid::pageWidth, pageWidthMm * MM_TO_INCH);
        style.set(engraving::Sid::pageHeight, pageHeightMm * MM_TO_INCH);
        style.set(engraving::Sid::pagePrintableWidth, (pageWidthMm - 2.5) * MM_TO_INCH);
        style.set(engraving::Sid::pageEvenLeftMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageOddLeftMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageEvenTopMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageEvenBottomMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageOddTopMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageOddBottomMargin, 1.25 * MM_TO_INCH);
        style.set(engraving::Sid::pageTwosided, false);
        style.set(engraving::Sid::spatium, 1.4);
        style.set(engraving::Sid::staffUpperBorder, engraving::Spatium(0.5));
        style.set(engraving::Sid::staffLowerBorder, engraving::Spatium(0.5));
        style.set(engraving::Sid::minSystemDistance, engraving::Spatium(0.5));
        style.set(engraving::Sid::maxSystemDistance, engraving::Spatium(1.0));
        style.set(engraving::Sid::enableVerticalSpread, false);
        score->setShowUnprintable(false);
        score->setShowFrames(false);

        if (state.titleBox) {
            state.titleBox->setVisible(false);
            state.titleBox->setAutoSizeEnabled(false);
            state.titleBox->setBoxHeight(engraving::Spatium(0.0));
            state.titleBox->setTopGap(engraving::Spatium(0.0));
            state.titleBox->setBottomGap(engraving::Spatium(0.0));
        }

        int measureIndex = 0;
        for (engraving::MeasureBase* item = score->first(); item; item = item->next()) {
            if (!item->isMeasure()) {
                continue;
            }
            ++measureIndex;
            const bool hasNextMeasure = item->nextMeasure() != nullptr;
            item->setLineBreak(false);
            item->setPageBreak(false);
            item->setSectionBreak(false);
            item->setNoBreak(false);
            if (hasNextMeasure) {
                item->undoSetBreak(measureIndex % 6 == 0,
                                   measureIndex % 6 == 0
                                   ? engraving::LayoutBreakType::PAGE
                                   : engraving::LayoutBreakType::LINE);
            }
        }
        state.portraitApplied = true;
        changed = true;
    } else if (!portrait && state.portraitApplied) {
        engraving::MStyle& style = score->style();
        style.set(engraving::Sid::pageWidth, state.pageWidth);
        style.set(engraving::Sid::pageHeight, state.pageHeight);
        style.set(engraving::Sid::pagePrintableWidth, state.pagePrintableWidth);
        style.set(engraving::Sid::pageEvenLeftMargin, state.pageEvenLeftMargin);
        style.set(engraving::Sid::pageOddLeftMargin, state.pageOddLeftMargin);
        style.set(engraving::Sid::pageEvenTopMargin, state.pageEvenTopMargin);
        style.set(engraving::Sid::pageEvenBottomMargin, state.pageEvenBottomMargin);
        style.set(engraving::Sid::pageOddTopMargin, state.pageOddTopMargin);
        style.set(engraving::Sid::pageOddBottomMargin, state.pageOddBottomMargin);
        style.set(engraving::Sid::pageTwosided, state.pageTwosided);
        style.set(engraving::Sid::spatium, state.spatium);
        style.set(engraving::Sid::staffUpperBorder, engraving::Spatium::fromAbsolute(
                       state.staffUpperBorder, state.spatium));
        style.set(engraving::Sid::staffLowerBorder, engraving::Spatium::fromAbsolute(
                       state.staffLowerBorder, state.spatium));
        style.set(engraving::Sid::minSystemDistance, engraving::Spatium::fromAbsolute(
                       state.minSystemDistance, state.spatium));
        style.set(engraving::Sid::maxSystemDistance, engraving::Spatium::fromAbsolute(
                       state.maxSystemDistance, state.spatium));
        style.set(engraving::Sid::enableVerticalSpread, state.verticalSpread);
        score->setShowUnprintable(state.showUnprintable);
        score->setShowFrames(state.showFrames);

        if (state.titleBox) {
            state.titleBox->setVisible(state.titleVisible);
            state.titleBox->setAutoSizeEnabled(state.titleAutoSize);
            state.titleBox->setBoxHeight(engraving::Spatium::fromAbsolute(state.titleHeight, state.spatium));
            state.titleBox->setTopGap(engraving::Spatium::fromAbsolute(state.titleTopGap, state.spatium));
            state.titleBox->setBottomGap(engraving::Spatium::fromAbsolute(state.titleBottomGap, state.spatium));
        }

        for (const detail::PlayerLayoutState::BreakState& item : state.breaks) {
            item.item->setLineBreak(item.lineBreak);
            item.item->setPageBreak(item.pageBreak);
            item.item->setSectionBreak(item.sectionBreak);
            item.item->setNoBreak(item.noBreak);
            item.item->cleanupLayoutBreaks(false);
        }
        state.portraitApplied = false;
        changed = true;
    }

    if (!changed) {
        return true;
    }

    notation->viewState()->setViewMode(notation::ViewMode::PAGE);
    notation->painting()->setViewMode(notation::ViewMode::PAGE);
    score->styleChanged();
    score->doLayout();
    score->update();

    const auto action = portrait
                        ? muse::actions::ActionCode("command://notation/view/zoom-to-whole-page")
                        : muse::actions::ActionCode("command://notation/view/zoom-to-page-width");
    dispatcher()->dispatch(action);
    return true;
}

void WebApi::onProjectSaved(const muse::io::path_t& path, mu::project::SaveMode)
{
    IF_ASSERT_FAILED(io::File::exists(path)) {
        LOGE() << "file does not exist, path: " << path;
        return;
    }

    ByteArray data;
    Ret ret  = io::File::readFile(path, data);
    if (!ret) {
        LOGE() << "failed read file, path: " << path;
        return;
    }

    callJsWithBytes("onProjectSaved", data.constData(), data.size());
}
