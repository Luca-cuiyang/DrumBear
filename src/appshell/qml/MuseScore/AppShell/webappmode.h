/*
 * SPDX-License-Identifier: GPL-3.0-only
 */

#pragma once

#include <QObject>
#include <qqmlintegration.h>

namespace mu::appshell {
class WebAppMode : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QString productMode READ productMode CONSTANT)
    Q_PROPERTY(bool studioPlayerMode READ studioPlayerMode CONSTANT)

    QML_ELEMENT
    QML_SINGLETON

public:
    explicit WebAppMode(QObject* parent = nullptr);

    QString productMode() const;
    bool studioPlayerMode() const;

private:
    QString m_productMode;
};
}
