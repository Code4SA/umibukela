Umibukela.Site = function() {
  var self = this;

  self.init = function() {
    self.colours = ['#f6921d', '#ccc'];

    // TODO: do this better
    self.drawCharts();
  };

  self.drawCharts = function() {
    var pct = !(!!window.chartValues);
    var valueKey = pct ? 'pct' : 'count';

    Highcharts.setOptions({
      credits: {enabled: false},
      chart: {animation: false},
      colors: self.colours,
      title: {text: null},
      xAxis: {
        lineWidth: 0,
        tickWidth: 0,
      },
      yAxis: {visible: false},
      legend: {enabled: false},
      tooltip: {
        formatter: function() {
          return '<b>' + this.x + ': ' + this.y + (pct ? '%' : '') + '</b><br>' + this.series.name;
        }
      },
      plotOptions: {
        series: {
          animation: false,
          pointPadding: 0.0,
          groupPadding: 0.07,
        },
        column: {
          dataLabels: {
            enabled: true,
            format: '{y}' + (pct ? '%' : ''),
          },
        },
        bar: {
          dataLabels: {
            enabled: true,
            format: '{y}' + (pct ? '%' : ''),
          },
        },
      },
    });

    $('.chart').each(function(i) {
      var $e = $(this);
      var chartIdFields = $e.data('indicator').split(":");
      var key = chartIdFields[0];
      var gender = chartIdFields[1];
      var q = questions[key];
      var chartType = $e.hasClass('chart-bar') ? 'bar' : 'column';
      var labels = _.map(q.options, function(o) { return o.current.label; });
      var currValues = _.map(q.options, function(o) {
          return Math.round(o.current[valueKey][gender]);
      });

      var series = [{
          data: currValues,
          stack: 'current',
          name: 'Current cycle',
          color: self.colours[0],
      }];

      var prevValues = [];
      _.map(q.options, function(o) {
          if (o.prev !== undefined) {
              prevValues.push(Math.round(o.prev[valueKey][gender]));
          }
      });
      if (prevValues.length === currValues.length) {
          var prevSeries = {
              data: prevValues,
              stack: 'historical',
              name: 'Previous cycle',
              dataLabels: {
                  enabled: false,
              },
              pointWidth: chartType == 'bar' ? 5 : 10,
              color: self.colours[1],
          };
          series.push(prevSeries);
          if (chartType == 'bar') {
              // show the current value on top. bar charts are drawn bottom up
              series = series.reverse();
          }
      }
      $(this).highcharts({
        chart: {type: chartType},
        series: series,
        xAxis: {
          categories: labels,
          labels: {step: 1},
        },
      });
    });
  };
};

$(function() {
  Umibukela.site = new Umibukela.Site();
  Umibukela.site.init();
});
