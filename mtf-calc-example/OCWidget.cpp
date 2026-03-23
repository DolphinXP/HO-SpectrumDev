#include "OCWidget.h"

#include <QModelIndex>
#include <QSize>

#include "./ui_OCWidget.h"

OCWidget::OCWidget(const QString& channelName, QWidget* parent)
    : QWidget(parent),
      channelName(channelName),
      dnmat(nullptr),
      ui(new Ui::OCWidget) {
  ui->setupUi(this);
  ui->labelTitle->setText(channelName + " - 光校");

  // Create layouts (without parent to avoid ownership issues)
  horizontalLayout = new QHBoxLayout();
  verticalLayout = new QVBoxLayout();

  // Store widget pointers for easy access
  widgets.append(ui->groupSetting);
  widgets.append(ui->tableDNNear);
  widgets.append(ui->dnAxisNearX);
  widgets.append(ui->dnAxisNearY);
  widgets.append(ui->dnAxisX);
  widgets.append(ui->dnAxisY);

  // Create container widget
  containerWidget = new QWidget();

  // By default, start with vertical layout
  containerWidget->setLayout(verticalLayout);

  // Add widgets to the current layout
  for (QWidget* widget : widgets) {
    verticalLayout->addWidget(widget);
  }

  // Create scroll area
  scrollArea = new QScrollArea(this);
  scrollArea->setWidgetResizable(true);
  scrollArea->setWidget(containerWidget);

  // scrollArea->setStyleSheet("border: none;");

  // Create main layout
  QVBoxLayout* mainLayout = new QVBoxLayout(this);
  mainLayout->addWidget(scrollArea);
  setLayout(mainLayout);

  // Track which layout is active
  currentLayoutIsHorizontal = false;

  // MTF
  ui->cmbMTFAvg->addItem("每1帧计算");
  ui->cmbMTFAvg->addItem("每5帧计算");
  ui->cmbMTFAvg->addItem("每10帧计算");
  connect(ui->cmbMTFAvg, QOverload<int>::of(&QComboBox::currentIndexChanged),
          [=](int index) {
            mtfAvgCount = 0;

            mtfAbove = 0.0;
            mtfBelow = 0.0;
            mtfLeft = 0.0;
            mtfRight = 0.0;
            mtfMean = 0.0;

            switch (index) {
              case 0:
                mtfAvgAccumulate = 1;
                break;
              case 1:
                mtfAvgAccumulate = 5;
                break;
              case 2:
                mtfAvgAccumulate = 10;
                break;
              default:
                break;
            }
          });
  ui->cmbMTFAvg->setCurrentIndex(0);

  // Tables
  model = new QStandardItemModel(this);
  // Initialize model with 9x9 items with value "-"
  model->setRowCount(9);
  model->setColumnCount(9);
  for (int row = 0; row < 9; ++row) {
    for (int col = 0; col < 9; ++col) {
      QStandardItem* item = new QStandardItem("-");
      model->setItem(row, col, item);
    }
  }
  ui->tableDNNear->setModel(model);
  ui->tableDNNear->setEditTriggers(QAbstractItemView::NoEditTriggers);
  // when click cell, jump to position
  connect(ui->tableDNNear, &QTableView::clicked, this,
          &OCWidget::onTableCellClicked);

  connect(ui->spinCol, &QSpinBox::valueChanged, this,
          &OCWidget::onSpinBoxValueChanged);
  connect(ui->spinRow, &QSpinBox::valueChanged, this,
          &OCWidget::onSpinBoxValueChanged);
  onSpinBoxValueChanged(0);  // Initialize the table with default values

  // button: jump to max
  connect(ui->btnJumpToMax, &QPushButton::clicked, this,
          &OCWidget::onJumpToMaxClicked);
}

OCWidget::~OCWidget() { delete ui; }

void OCWidget::onSpinBoxValueChanged(int value) {
  int x = ui->spinCol->value();
  int y = ui->spinRow->value();
  // No need to clear the model, just update the headers

  // Set up headers
  QStringList headers;
  for (int i = x - 4; i <= x + 4; ++i) {
    headers << QString::number(i);
  }
  model->setHorizontalHeaderLabels(headers);

  QStringList verticalHeaders;
  for (int i = y - 4; i <= y + 4; ++i) {
    verticalHeaders << QString::number(i);
  }
  model->setVerticalHeaderLabels(verticalHeaders);

  // Set column width
  for (int i = 0; i < model->columnCount(); ++i) {
    ui->tableDNNear->setColumnWidth(i, 50);
  }
}
void OCWidget::setCursorPos(int col, int row) {
  ui->spinCol->setValue(col);
  ui->spinRow->setValue(row);
  ui->dnAxisX->setCursorPos(col, row);
  ui->dnAxisY->setCursorPos(col, row);
  ui->dnAxisNearX->setCursorPos(col, row);
  ui->dnAxisNearY->setCursorPos(col, row);
}

void OCWidget::setParam(int cols, int rows, uint8_t pixelDepth) {
  this->cols = cols;
  this->rows = rows;

  ui->spinCol->setRange(0, cols - 1);
  ui->spinCol->setValue(cols / 2);
  ui->spinRow->setRange(0, rows - 1);
  ui->spinRow->setValue(rows / 2);

  QSize imgSize = QSize(cols, rows);
  int maxValue = (1 << pixelDepth) - 1;

  ui->dnAxisX->SetParam(QString::fromUtf8("全域空间维(行)"), DN_CONT_LINE,
                        "Range", "DN", 0, maxValue, DN_IMG_HORIZONTAL, imgSize);

  ui->dnAxisY->SetParam(QString::fromUtf8("全域光谱维(列)"), DN_CONT_LINE,
                        "Range", "DN", 0, maxValue, DN_IMG_VERTICAL, imgSize);

  ui->dnAxisNearX->SetParam(QString::fromUtf8("临近空间维(行)"), DN_STEP_LINE,
                            "Range", "DN", 0, maxValue, DN_IMG_HORIZONTAL,
                            imgSize);

  ui->dnAxisNearY->SetParam(QString::fromUtf8("临近光谱维(列)"), DN_STEP_LINE,
                            "Range", "DN", 0, maxValue, DN_IMG_VERTICAL,
                            imgSize);
}

void OCWidget::setData(uint16_t* dnmat) {
  this->dnmat = dnmat;

  ui->dnAxisX->setData(dnmat);
  ui->dnAxisY->setData(dnmat);
  ui->dnAxisNearX->setData(dnmat);
  ui->dnAxisNearY->setData(dnmat);
  // ui->tableDNNear->SetData(dnmat);

  int x = ui->spinCol->value();
  int y = ui->spinRow->value();

  for (int row = 0; row < model->rowCount(); ++row) {
    for (int col = 0; col < model->columnCount(); ++col) {
      int dnRow = y - 4 + row;
      int dnCol = x - 4 + col;
      auto item = model->item(row, col);
      if (dnRow < 0 || dnCol < 0 || dnRow > (rows - 1) || dnCol > (cols - 1)) {
        item->setText("-");
      } else {
        int index = dnRow * (cols) + dnCol;
        item->setText(QString::number(dnmat[index]));
      }
    }
  }

  // 不计算了，直接拿来
  bool ok = false;
  dnCenter = model->item(4, 4)->text().toDouble(&ok);
  if (!ok) dnCenter = std::numeric_limits<double>::quiet_NaN();
  dnAbove = model->item(3, 4)->text().toDouble(&ok);
  if (!ok) dnAbove = std::numeric_limits<double>::quiet_NaN();
  dnBelow = model->item(5, 4)->text().toDouble(&ok);
  if (!ok) dnBelow = std::numeric_limits<double>::quiet_NaN();
  dnLeft = model->item(4, 3)->text().toDouble(&ok);
  if (!ok) dnLeft = std::numeric_limits<double>::quiet_NaN();
  dnRight = model->item(4, 5)->text().toDouble(&ok);
  if (!ok) dnRight = std::numeric_limits<double>::quiet_NaN();

  updateMTF();
}

void OCWidget::resizeEvent(QResizeEvent* event) {
  QWidget::resizeEvent(event);

  bool shouldBeHorizontal = width() > height();

  // Only switch layouts if the orientation changes
  if (shouldBeHorizontal != currentLayoutIsHorizontal) {
    switchLayout(shouldBeHorizontal);
  }
}

void OCWidget::switchLayout(bool toHorizontal) {
  // Create a new layout
  QLayout* newLayout = toHorizontal ? static_cast<QLayout*>(new QHBoxLayout())
                                    : static_cast<QLayout*>(new QVBoxLayout());

  // Move widgets to the new layout
  for (QWidget* widget : widgets) {
    widget->setParent(nullptr);  // Detach from current parent
    newLayout->addWidget(widget);
  }

  // Delete the old layout
  delete containerWidget->layout();

  // Set the new layout
  containerWidget->setLayout(newLayout);

  // Update the tracking variable
  currentLayoutIsHorizontal = toHorizontal;
}

// MTF

void OCWidget::updateMTF() {
  const int x = ui->spinCol->value();
  const int y = ui->spinRow->value();
  QString sLeft = "无效值";
  QString sRight = "无效值";
  QString sAbove = "无效值";
  QString sBelow = "无效值";
  QString s_mean = "无效值";

  mtfAbove += calcMTF(dnCenter, dnAbove, ui->spinDarkValue->value());
  mtfBelow += calcMTF(dnCenter, dnBelow, ui->spinDarkValue->value());
  mtfLeft += calcMTF(dnCenter, dnLeft, ui->spinDarkValue->value());
  mtfRight += calcMTF(dnCenter, dnRight, ui->spinDarkValue->value());
  // mtf_center = (mtf_left + mtf_right) / 2;
  if (++mtfAvgCount >= mtfAvgAccumulate) {
    mtfAbove /= mtfAvgAccumulate;
    mtfBelow /= mtfAvgAccumulate;
    mtfLeft /= mtfAvgAccumulate;
    mtfRight /= mtfAvgAccumulate;

    if (x - 1 < 0) {
      // mtfAbove = mtfBelow = mtfRight = mtfMean = 0.0;
      mtfLeft = std::numeric_limits<double>::quiet_NaN();
      mtfAvgCount = 0;
    }
    if (x + 1 >= cols) {
      // mtfAbove = mtfBelow = mtfLeft = mtfMean = 0.0;
      mtfRight = std::numeric_limits<double>::quiet_NaN();
      mtfAvgCount = 0;
    }
    if (y - 1 < 0) {
      // mtfAbove = mtfBelow = mtfLeft = mtfRight = mtfMean = 0.0;
      mtfAbove = std::numeric_limits<double>::quiet_NaN();
      mtfAvgCount = 0;
    }
    if (y + 1 >= rows) {
      // mtfAbove = mtfBelow = mtfLeft = mtfRight = mtfMean = 0.0;
      mtfBelow = std::numeric_limits<double>::quiet_NaN();
      mtfAvgCount = 0;
    }

    mtfMean = (mtfAbove + mtfBelow + mtfLeft + mtfRight) / 4.0;

    if (!std::isnan(mtfAbove)) {
      sAbove = QString::number(mtfAbove, 'f', 3);
    }
    if (!std::isnan(mtfBelow)) {
      sBelow = QString::number(mtfBelow, 'f', 3);
    }
    if (!std::isnan(mtfLeft)) {
      sLeft = QString::number(mtfLeft, 'f', 3);
    }
    if (!std::isnan(mtfRight)) {
      sRight = QString::number(mtfRight, 'f', 3);
    }
    if (!std::isnan(mtfMean)) {
      s_mean = QString::number(mtfMean, 'f', 3);
    }

    mtfAbove = mtfBelow = mtfLeft = mtfRight = mtfMean = 0.0;
    mtfAvgCount = 0;

    ui->lblAboveMTF->setText(sAbove);
    ui->lblBelowMTF->setText(sBelow);
    ui->lblLeftMTF->setText(sLeft);
    ui->lblRightMTF->setText(sRight);
    ui->lblMeanMTF->setText(s_mean);
  }
}

void OCWidget::onTableCellClicked() {
  QModelIndex index = ui->tableDNNear->currentIndex();
  if (index.isValid()) {
    int row = index.row();

    int column = index.column();
    // Get horizontal header (column header)
    QVariant columnHeader =
        ui->tableDNNear->model()->headerData(column, Qt::Horizontal);
    int x = columnHeader.toInt();

    // Get vertical header (row header)
    QVariant rowHeader =
        ui->tableDNNear->model()->headerData(row, Qt::Vertical);
    int y = rowHeader.toInt();

    // qDebug() << "Row:" << row << "Column:" << column;
    // qDebug() << "Column Header:" << x;
    // qDebug() << "Row Header:" << y;

    ui->spinRow->setValue(y);
    ui->spinCol->setValue(x);
  }
}

void OCWidget::onJumpToMaxClicked() {
  if (!dnmat) {
    return;
  }

  int maxIndex = 0;
  uint16_t maxValue = dnmat[0];
  for (int i = 1; i < rows * cols; ++i) {
    if (dnmat[i] > maxValue) {
      maxValue = dnmat[i];
      maxIndex = i;
    }
  }
  int row = maxIndex / cols;
  int col = maxIndex % cols;
  ui->spinRow->setValue(row);
  ui->spinCol->setValue(col);
}

double OCWidget::calcMTF(double dnCurr, double dnNear, double blackLevel) {
  double A = dnCurr - blackLevel;
  double B = dnNear - blackLevel;
  return ((A - B) / (A + B)) * M_PI_4;
}