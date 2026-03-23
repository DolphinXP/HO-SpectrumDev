#ifndef OCWIDGET_H
#define OCWIDGET_H

#include <QHBoxLayout>
#include <QList>
#include <QResizeEvent>
#include <QScrollArea>
#include <QStandardItemModel>
#include <QVBoxLayout>
#include <QWidget>

namespace Ui {
class OCWidget;
}

class OCWidget : public QWidget {
  Q_OBJECT

 public:
  explicit OCWidget(const QString& channelName, QWidget* parent = nullptr);
  ~OCWidget();
  void setParam(int cols, int rows, uint8_t pixelDepth);
  void setData(uint16_t* dnmat);
  void setCursorPos(int col, int row);
 protected:
  void resizeEvent(QResizeEvent* event) override;

 private slots:
  void onSpinBoxValueChanged(int value);
  void updateMTF();
  void onTableCellClicked();
  void onJumpToMaxClicked();

 private:
  void switchLayout(bool toHorizontal);
  double calcMTF(double dnCurr, double dnNear, double blackLevel);

  Ui::OCWidget* ui;
  QString channelName;
  int rows;
  int cols;

  uint16_t* dnmat;

  QHBoxLayout* horizontalLayout;
  QVBoxLayout* verticalLayout;
  QWidget* containerWidget;
  QScrollArea* scrollArea;
  QList<QWidget*> widgets;
  bool currentLayoutIsHorizontal;

  // MTF
  uint16_t dnAbove, dnBelow, dnLeft, dnRight, dnCenter;
  double mtfAbove, mtfBelow, mtfLeft, mtfRight,
      mtfMean;  // mtf sum -> average
  int mtfAvgCount = 0;
  int mtfAvgAccumulate = 1;

  QStandardItemModel* model;
};

#endif  // OCWIDGET_H