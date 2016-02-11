# gs2_3d_flux_tube plots 3D flux tubes and outputs the data in useful formats.
# Copyright (C) 2016  Ferdinand van Wyk
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import configparser

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from netCDF4 import Dataset
import f90nml as nml
# from pyevtk.hl import gridToVTK
plt.rcParams.update({'figure.autolayout': True})
mpl.rcParams['axes.unicode_minus'] = False

class Run(object):
    """
    Run object which stores basic simulation information.
    """

    def __init__(self, config_file):
        """
        Initialize with NetCDF file information.
        """

        self.config_file = config_file

        self.read_config()
        self.find_run_dir()
        self.extract_input_file()
        self.read_input_file()
        self.read_netcdf()
        self.calculate_gs2_coords()
        self.calculate_cyl_coords()
        self.calculate_cart_coords()

    def read_config(self):
        """
        Read parameters from the config file.
        """

        config = configparser.ConfigParser()
        config.read(self.config_file)

        self.cdf_file = str(config['io']['cdf_file'])
        self.rho_tor = float(config['normalizations']['rho_tor'])
        self.amin = float(config['normalizations']['amin'])
        self.vth = float(config['normalizations']['vth'])
        self.rho_ref = float(config['normalizations']['rho_ref'])

    def find_run_dir(self):
        """
        Determine the run directory based on the location of the NetCDF file.

        Default is current directory.
        """

        try:
            idx = self.cdf_file.rindex('/')
            self.run_dir = self.cdf_file[:idx] + '/'
        except ValueError:
            self.run_dir = ''

    def read_netcdf(self):
        """
        Read data from the netcdf file.
        """

        self.cdf_obj = Dataset(self.cdf_file, 'r')

        self.drho_dpsi = ncfile.variables['drhodpsi'][0]
        self.kx = np.array(ncfile.variables['kx'][:])
        self.ky = np.array(ncfile.variables['ky'][:])
        self.theta = np.array(ncfile.variables['theta'][:])
        self.t = np.array(ncfile.variables['t'][:])
        self.gradpar = np.array(ncfile.variables['gradpar'][:])
        self.grho = np.array(ncfile.variables['grho'][:])
        self.bmag = np.array(ncfile.variables['bmag'][:])
        self.dtheta = np.append(np.diff(self.theta), 0)
        self.r_0 = np.array(ncfile.variables['Rplot'][:])*self.amin
        self.rprime = np.array(ncfile.variables['Rprime'][:])*self.amin
        self.z_0 = np.array(ncfile.variables['Zplot'][:])*self.amin
        self.zprime = np.array(ncfile.variables['Zprime'][:])*self.amin
        self.alpha_0 = np.array(ncfile.variables['aplot'][:])
        self.alpha_prime = np.array(ncfile.variables['aprime'][:])

        self.n0 = (int(np.around(self.ky[1] / self.drho_dpsi *
                   (self.amin/self.rhoref))))
        self.nt = len(self.t)
        self.nkx = len(self.kx)
        self.nky = len(self.ky)
        self.nth = len(self.theta)
        self.nx = self.nkx
        self.ny = 2*(self.nky - 1)
        self.t = self.t*self.amin/self.vth

        self.correct_geometry()

        self.read_phi()
        self.read_ntot()
        self.read_upar()
        self.read_tpar()
        self.read_tperp()

        self.cdf_obj.close()

    def read_phi(self):
        """
        Read the electrostatic potential from the NetCDF file.
        """

        self.phi = self.read_field('phi', None)
        self.phi = self.field_to_real_space(self.phi)*self.rho_star

    def read_ntot(self):
        """
        Read the density from the NetCDF file.
        """

        self.ntot_i = self.read_field('ntot', 0)
        self.ntot_e = self.read_field('ntot', 1)

        self.ntot_i = self.field_to_real_space(self.ntot_i)*self.rho_star
        self.ntot_e = self.field_to_real_space(self.ntot_e)*self.rho_star

    def read_upar(self):
        """
        Read the parallel velocity.
        """

        self.upar_i = self.read_field('upar', 0)
        self.upar_e = self.read_field('upar', 1)

        self.upar_i = self.field_to_real_space(self.upar_i)*self.rho_star
        self.upar_e = self.field_to_real_space(self.upar_e)*self.rho_star

    def read_tpar(self):
        """
        Read the parallel temperature.
        """

        self.tpar_i = self.read_field('tpar', 0)
        self.tpar_e = self.read_field('tpar', 1)

        self.tpar_i = self.field_to_real_space(self.tpar_i)*self.rho_star
        self.tpar_e = self.field_to_real_space(self.tpar_e)*self.rho_star

    def read_tperp(self):
        """
        Read the perpendicular temperature.
        """

        self.tperp_i = self.read_field('tperp', 0)
        self.tperp_e = self.read_field('tperp', 1)

        self.tperp_i = self.field_to_real_space(self.tperp_i)*self.rho_star
        self.tperp_e = self.field_to_real_space(self.tperp_e)*self.rho_star

    def read_field(self, field_name, spec_idx):
        """
        Read field from ncfile and prepare for calculations.

        * Read from NetCDF file
        * Swap axes order to be (t, x, y)
        * Convert to complex form
        * Apply GS2 fourier correction
        """

        if spec_idx == None:
            field = np.array(self.cdf_obj.variables[field_name][:,:,:,:])
        else:
            field = np.array(cdf_obj.variables[field_name][spec_idx,:,:,:,:])

        field = np.swapaxes(field, 0, 1)
        field = field[:,:,:,0] + 1j*field[:,:,:,1]

        field[:,1:,:] = field[:,1:,:]/2

        return(field)

    def field_to_real_space(self, field):
        """
        Converts a field from (kx, ky, theta) to (x, y, theta).
        """
        shape = field.shape
        nx = shape[0]
        nky = shape[1]
        nth = shape[2]
        ny = 2*(nky - 1)

        field_real_space = np.empty([nx,ny,nth],dtype=float)
        field_real_space = np.fft.irfft2(field, axes=[0,1])
        field_real_space = np.roll(field_real_space, int(nx/2), axis=0)

        return field_real_space*nx*ny

    def extract_input_file(self):
        """
        Extract the GS2 input file from the NetCDF file to the run dir..
        """

        # Taken from extract_input_file in the GS2 scripts folder:
        #1: Get the input_file variable from the netcdf file
        #2: Only print lines between '${VAR} = "' and '" ;'
        # (i.e. ignore header and footer)
        #3: Convert \\n to new lines
        #4: Delete empty lines
        #5: Ignore first line
        #6: Ignore last line
        #7: Fix " style quotes
        #8: Fix ' style quotes
        bash_extract_input = (""" ncdump -v input_file ${FILE} | """ +
                          """ sed -n '/input_file = /,/" ;/p' | """ +
                          """ sed 's|\\\\\\\\n|\\n|g' | """ +
                          """ sed '/^ *$/d' | """ +
                          """ tail -n+2 | """ +
                          """ head -n-2 | """ +
                          """ sed 's|\\\\\\"|\\"|g' | """ +
                          """ sed "s|\\\\\\'|\\'|g" """)
        os.system('FILE=' + self.cdf_file + '; ' +
                  bash_extract_input + ' > ' +
                  self.run_dir + 'input_file.in')
        self.gs2_in = nml.read(self.run_dir + 'input_file.in')

    def read_input_file(self):
        """
        Read the GS2 input file extracted from the NetCDF file.
        """

        self.g_exb = float(gs2_in['dist_fn_knobs']['g_exb'])
        self.rhoc = float(gs2_in['theta_grid_parameters']['rhoc'])
        self.qinp = float(gs2_in['theta_grid_parameters']['qinp'])
        self.shat = float(gs2_in['theta_grid_parameters']['shat'])
        self.jtwist = float(gs2_in['kt_grids_box_parameters']['jtwist'])
        self.tprim_1 = float(gs2_in['species_parameters_1']['tprim'])
        self.fprim_1 = float(gs2_in['species_parameters_1']['fprim'])
        self.mass_1 = float(gs2_in['species_parameters_1']['mass'])
        if gs2_in['species_knobs']['nspec'] == 2:
            self.tprim_2 = float(gs2_in['species_parameters_2']['tprim'])
            self.fprim_2 = float(gs2_in['species_parameters_2']['fprim'])
            self.mass_2 = float(gs2_in['species_parameters_2']['mass'])

    def correct_geometry(self):
        """
        Correct the geometry parameters using Applegate notes.

        After calculating an integer n0, need to recalculate the alpha and
        alpha_prime geometry parameters which are used to calculate the
        toroidal angle phi.
        """

        # Calculate rho_star using integer n0:
        self.rho_star = self.ky[1] / self.n0 / self.drho_dpsi

        # Set q to closest rational q
        self.m_mode = int(np.around(self.qinp*self.n0))
        self.q_rational = float(self.m_mode)/float(self.n0)

        # Correct alpha read in from geometry
        self.alpha_0_corrected = (self.alpha_0 + (self.qinp - self.q_rational)*
                                                self.theta)

        # Correct alpha_prime
        self.q_prime = (abs((self.alpha_prime[0] - self.alpha_prime[-1]) /
                           (2*np.pi)))
        self.delta_rho = ((self.rho_tor/self.q_rational) *
                         (self.jtwist/(self.n0*self.shat)))
        self.q_prime_corrected = self.jtwist / (self.n0 * self.delta_rho)
        self.alpha_prime_corrected = (self.alpha_prime + (self.q_prime -
                                        self.q_prime_corrected)*self.theta)

    def calculate_gs2_coords(self):
        """
        Calculate the real space (x, y) GS2 grids.
        """

        self.x = 2*np.pi*np.linspace(0, 1/self.kx[1], self.nx, endpoint=False)
        self.y = 2*np.pi*np.linspace(0, 1/self.ky[1], self.ny, endpoint=False)

    def calculate_cyl_coords(self):
        """
        Calculate the cylindrical coordinates (R, Z, phi).
        """

        # Calculate (rho - rho_n0) and call it rho_n and alpha
        self.rho_n = (self.x * self.rhoc / self.q_rational * self.drho_dpsi *
                      self.rho_star)
        self.alpha = self.y * self.drho_dpsi * self.rho_star

        self.R = np.empty([self.nx, self.ny, self.nth], dtype=float)
        self.Z = np.empty([self.nx, self.ny, self.nth], dtype=float)
        self.phi_tor = np.empty([self.nx, self.ny, self.nth], dtype=float)
        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nth):
                    self.R[i,j,k] = self.r_0[k] + self.rho_n[i]*self.rprime[k]
                    self.Z[i,j,k] = self.z_0[k] + self.rho_n[i]*self.zprime[k]
                    self.phi_tor[i,j,k] = (self.alpha[j] -
                                           self.alpha_0_corrected[k] -
                                           self.rho_n[i]*
                                           self.alpha_prime_corrected[k])

    def calculate_cart_coords(self):
        """
        Calculate the cartesian coordinates (X, Y). Note that Z is already
        calculated in the calculate_cyl_coords method.
        """

        self.X = self.R * np.cos(self.phi_tor)
        self.Y = self.R * np.sin(self.phi_tor)

if __name__ == '__main__':

    run = Run(sys.argv[1])

    fig = plt.figure()
    ax = plt.add_suplot(111, projection='3d')
    ax.scatter(run.X, run.Y, run.Z)
    plt.show()