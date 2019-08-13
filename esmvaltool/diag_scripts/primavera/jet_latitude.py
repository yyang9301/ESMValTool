import os
import logging

import matplotlib.pyplot as plt

import numpy as np
from scipy import stats

import iris
import iris.cube
import iris.analysis
import iris.util
import iris.coord_categorisation
import iris.quickplot as qp

import esmvaltool.diag_scripts.shared
import esmvaltool.diag_scripts.shared.names as n
from esmvaltool.diag_scripts.shared import group_metadata

logger = logging.getLogger(os.path.basename(__file__))


class JetLatitude(object):
    def __init__(self, config):
        self.cfg = config
        self.filenames = esmvaltool.diag_scripts.shared.Datasets(self.cfg)
        self.output_name = None
        self.target_grid = self.cfg.get('target_grid')
        self.grid_cube = None
        self.sftlf = None

    def compute(self):
        data = group_metadata(self.cfg['input_data'].values(), 'alias')
        lanczos_weight = np.load(
            '/home/users/panos/work_space/jetlat/python/LF_weights.npy'
        )
        for alias in data:
            ua = iris.load_cube(data[alias][0]['filename'])
            iris.coord_categorisation.add_season(ua, 'time')

            ua_filtered = np.apply_along_axis(
                lambda m: np.convolve(m, lanczos_weight, mode='same'),
                axis=ua.coord_dims('time')[0],
                arr=ua.core_data()
            )
            ua = ua.copy(ua_filtered)

            wind = ua.collapsed('latitude', iris.analysis.MAX)
            latitude = np.argmax(
                ua.data,
                axis=ua.coord_dims('latitude')[0]
            )
            del ua
            del ua_filtered
            latitude = wind.copy(latitude)
            latitude.var_name = 'lat'
            latitude.standard_name = 'latitude'
            latitude.long_name = 'Jet latitude'
            latitude.units = 'degrees_north'

            logger.debug(wind)
            logger.debug(latitude)

            self._compute_histogram(alias, wind)
            self._compute_histogram(alias, latitude)

    def _compute_histogram(self, alias, data):
        clim = data.aggregated_by('day_of_year', iris.analysis.MEAN)
        clim.remove_coord('time')
        clim.remove_coord('month_number')
        clim.remove_coord('day_of_month')
        clim.remove_coord('year')
        iris.util.promote_aux_coord_to_dim_coord(clim, 'day_of_year')
        clim_fft = np.fft.rfft(clim.data)
        clim_fft[3:np.size(clim_fft)] = 0
        clim_fft = np.fft.irfft(clim_fft)
        clim = clim.copy(clim_fft)

        anom = data.data
        day_year = data.coord('day_of_year').points
        for day_slice in clim.slices_over('day_of_year'):
            num_day = day_slice.coord('day_of_year').points[0]
            anom[day_year == num_day] = anom[day_year == num_day] - day_slice.data
        anom = data.copy(anom)
        qp.plot(data)
        plt.savefig(os.path.join(
            self.cfg[n.PLOT_DIR],
            '{}_{}_anom.png'.format(alias, data.var_name))
        )
        plt.close()
        season_clim = clim.aggregated_by('season', iris.analysis.MEAN)
        current_season = anom.coord('day_of_year').points
        latitude = anom.coord('latitude')
        for season_slice in season_clim.slices_over('season'):
            anom_slice = season_clim.extract(iris.Constraint(season=season_slice.coord('season').points[0]))
            season = season_slice.coord('season').points[0]
            anom_slice.data[current_season == season] = anom_slice.data[current_season == season] - season_slice.data
            hist, bin_edges = np.histogram(season_slice, bins=np.arange(latitude.min(), latitude.max(), 2.5)-1.25)
            kde = stats.gaussian_kde(season_slice.data)
            lats = np.linspace(bin_edges.min(), bin_edges.max(), 100)
            kde.set_bandwidth(bw_method='silverman')
            kde.set_bandwidth(bw_method=kde.factor*1.06)
            pdf = kde(lats)
            self._plot_histogram(alias, season_slice, hist, lats, pdf)

    def _plot_histogram(self, alias, season_slice, histogram, lats, pdf):
        season = season_slice.coord('season').points[0]
        lat_bounds = season.coord('latitude').bounds
        g = 0.4; G = 0.5
        plt.figure(figsize=(14, 8), dpi=250)
        plt.bar(
            season_slice.coord('latitude').points,
            histogram / 2.5 * histogram.sum(),
            width=2.5, align='center',
            color=[g,g,g], alpha=1, edgecolor=[G,G,G]
        )
        plt.plot(
            (np.mean(season_slice.data), np.mean(season_slice.data)), (0, 1),
            color=[0.7, 0.7, 0.7], lw=3, ls='--'
        )
        plt.plot(lats, pdf, color=[0.8, 0.2, 0.2], lw=3, ls='-')
        # --- X-axes properties ---
        plt.xlabel(u'Latitude (\u00B0N)')
        plt.xlim(lat_bounds.min(), lat_bounds.max())
        # --- Y-axes properties ---
        plt.ylabel('Relative Frequency Density')
        plt.ylim(0,0.1)
        plt.yticks([0, 0.02, 0.04, 0.06, 0.08, 0.1])
        plt.title('Jet-Latitude Distribution for ' + alias + ', ' + season + ' (1979-2016)')
        plt.grid()
        plt.savefig('{}_{}_{}.png'.format(season_slice.var_name, alias, season), bbox_inches='tight')

def main():
    with esmvaltool.diag_scripts.shared.run_diagnostic() as config:
        JetLatitude(config).compute()


if __name__ == '__main__':
    main()