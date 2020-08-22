
# -*- coding: utf-8 -*-

u'''Classes L{AlbersEqualArea}, L{AlbersEqualArea2}, L{AlbersEqualArea4},
L{AlbersEqualAreaCylindrical}, L{AlbersEqualAreaNorth}, L{AlbersEqualAreaSouth} and
L{AlbersError}, a transcription of I{Charles Karney}'s C++ class U{AlbersEqualArea
<https://GeographicLib.SourceForge.io/html/classGeographicLib_1_1AlbersEqualArea.html>}.

See also I{Albers Equal-Area Conic Projection} in U{John P. Snyder, "Map Projections
-- A Working Manual", 1987<https://pubs.er.USGS.gov/djvu/PP/PP_1395.pdf>}, pp 98-106
and the Albers Conical Equal-Area examples on pp 291-294.

@newfield example: Example, Examples
'''

from pygeodesy.basics import EPS, property_RO, _xinstanceof, _xkwds
from pygeodesy.datum import Datums, Datum
from pygeodesy.errors import _ValueError
from pygeodesy.fmath import Fsum, fsum_, hypot, hypot1, sqrt3
from pygeodesy.interns import _datum_, _gamma_, _lat_, _lat0_, \
                              _lat1_, _lat2_, _lon_, _lon0_, NN, \
                              _no_convergence_fmt_, _scale_, _x_, _y_
from pygeodesy.karney import _diff182, _norm180
from pygeodesy.lazily import _ALL_DOCS, _ALL_LAZY
from pygeodesy.named import _NamedBase, _NamedTuple, _xnamed
from pygeodesy.units import Degrees, Float_, Lat_, Lon_, Scalar, Scalar_
from pygeodesy.utily import atan2d, degrees360, sincos2, sincos2d

from math import atan, atan2, atanh, degrees, radians, sqrt

__all__ = _ALL_LAZY.albers
__version__ = '20.08.22'

_EPSX   = EPS**2
_EPSX2  = EPS**4
_NUMIT  =  8  # XXX 4?
_NUMIT0 = 41  # XXX 21?
_TERMS  = 21  # XXX 9?
_TOL    = sqrt(EPS)
_TOL0   = sqrt3(_TOL)


class AlbersError(_ValueError):
    '''An L{AlbersEqualArea}, L{AlbersEqualArea2}, L{AlbersEqualArea4},
       L{AlbersEqualAreaCylindrical}, L{AlbersEqualAreaNorth},
       L{AlbersEqualAreaSouth} or L{Albers7Tuple} issue.
    '''
    pass


def _Dsn(x, y, sx, sy):
    '''(INTERNAL) Divided differences, defined as
       M{Df(x, y) = (f(x) - f(y)) / (x - y)} with
       M{sn(x) = x / sqrt(1 + x^2)}: M{Dsn(x, y) =
       (x + y) / ((sn(x) + sn(y)) * (1 + x^2) * (1 + y^2))}.

       @see: U{W. M. Kahan and R. J. Fateman, "Sympbolic omputation of divided
             differences"<https://people.EECS.Berkeley.EDU/~fateman/papers/divdiff.pdf>},
             U{ACM SIGSAM Bulletin 33(2), 7-28 (1999)<https://doi.org/10.1145/334714.334716>}
             and U{AlbersEqualArea.hpp
             <https://geographiclib.sourceforge.io/html/AlbersEqualArea_8hpp_source.html>}.
    '''
    # sx = x / hypot1(x)
    d, t = 1, x * y
    if t > 0:
        s = sx + sy
        if s:
            d = (x + y) * ((sx * sy) / t)**2 / s
    else:
        t = x - y
        if t:
            d = (sx - sy) / t
    return d


def _Ks(k, name):
    '''(INTERNAL) Scale C{B{k} >= EPS}.
    '''
    return Scalar_(k, name=name, Error=AlbersError, low=EPS)  # > 0


def _Lat_(lat, name=_lat_):
    '''(INTERNAL) Latitude C{-90 <= B{lat} <= 90}.
    '''
    return Lat_(lat, name=name, Error=AlbersError)


def _Lon_(lon, name=_lon_):
    '''(INTERNAL) Longitude C{-180 <= B{lon} <= 180}.
    '''
    return Lon_(lon, name=name, Error=AlbersError)


def _tol(tol, x):
    '''(INTERNAL) Converge tolerance.
    '''
    return tol * max(1, abs(x))


class _AlbersBase(_NamedBase):
    '''(INTERNAL) Base class for C{AlbersEqualArea...} projections.

       @see: I{Karney}'s C++ class U{AlbersEqualArea<https://GeographicLib.SourceForge.io/
             html/classGeographicLib_1_1AlbersEqualArea.html>}, method C{Init}.
    '''
    _datum     = Datums.WGS84
    _iteration = None
    _lat0      = None  # lat origin
    _lat1      = None  # let 1st parallel
    _lat2      = None  # lat 2nd parallel
    _k0        = None  # scale
    _k0n0      = None  # (INTERNAL) k0 * no
    _k02       = None  # (INTERNAL) k0**2
    _k02n0     = None  # (INTERNAL) k02 * n0
    _m0        = 0.0   # if polar else sqrt(m02)
    _m02       = None  # (INTERNAL) cached
    _n0        = None  # (INTERNAL) cached
    _nrho0     = 0.0   # if polar else m0 * E.a
    _polar     = False
    _qx        = None  # (INTERNAL) cached
    _qZ        = None  # (INTERNAL) cached
    _qZa2      = None  # (INTERNAL) qZ * E.a**2
    _scxi0     = None  # (INTERNAL) sec(xi)
    _sign      = +1
    _sxi0      = None  # (INTERNAL) sin(xi)
    _txi0      = None  # (INTERNAL) tan(xi)

    def __init__(self, sa1, ca1, sa2, ca2, k, datum, name):
        '''(INTERNAL) New C{AlbersEqualArea...} instance.
        '''
        if datum and datum not in (None, self._datum):
            _xinstanceof(Datum, datum=datum)
            self._datum = datum
        if name:
            self.name = name

        E = self.datum.ellipsoid
        b_a = E.b_a  # fm  = 1 - E.f
        e2  = E.e2
        e12 = E.e12  # e2m = 1 - E.e2

        self._qZ   = qZ = 1 + e12 * self._atanhee(1)
        self._qZa2 = qZ * E.a2
        self._qx   = qZ / (2 * e12)

        c = min(ca1, ca2)
        if c < 0:
            raise AlbersError(clat1=ca1, clat2=ca2)
        polar = c < _EPSX  # == 0
        # determine hemisphere of tangent latitude
        if sa1 < 0:  # and sa2 < 0:
            self._sign = -1
            # internally, tangent latitude positive
            sa1, sa2 = -sa1, -sa2
        if sa1 > sa2:  # make phi1 < phi2
            sa1, sa2 = sa2, sa1
            ca1, ca2 = ca2, ca1
        if sa1 < 0:  # or sa2 < 0:
            raise AlbersError(slat1=sa1, slat2=sa2)
        # avoid singularities at poles
        ca1, ca2 = max(_EPSX, ca1), max(_EPSX, ca2)
        ta1, ta2 = sa1 / ca1, sa2 / ca2

        par1 = abs(ta1 - ta2) < _EPSX2  # ta1 == ta2
        if par1 or polar:
            C, ta0 = 1, ta2
        else:
            s1_qZ, C = self._s1_qZ_C2(ca1, sa1, ta1, ca2, sa2, ta2)

            ta0 = (ta2 + ta1) * 0.5
            Ta0 = Fsum(ta0)
            tol = _tol(_TOL0, ta0)
            for self._iteration in range(1, _NUMIT0):
                ta02  = ta0**2
                sca02 = ta02 + 1
                sca0  = sqrt(sca02)
                sa0   = ta0 / sca0
                sa01  = sa0 + 1
                sa02  = sa0**2
                # sa0m = 1 - sa0 = 1 / (sec(a0) * (tan(a0) + sec(a0)))
                sa0m  = 1 / (sca0 * (ta0 + sca0))  # scb0^2 * sa0
                g  = (1 + (b_a * ta0)**2) * sa0
                dg = e12 * sca02 * (1 + 2 * ta02) + e2
                D  = sa0m * (1 - e2 * (1 + sa01 * 2 * sa0)) / (e12 * sa01)  # dD/dsa0
                dD =   -2 * (1 - e2 * sa02 * (3 + 2 * sa0)) / (e12 * sa01**2)
                sa02_ = 1 - e2 * sa02
                sa0m_ = sa0m / (1 - e2 * sa0)
                BA = sa0m_ * (self._atanhx1(e2 * sa0m_**2) * e12 - e2 * sa0m) \
                   - sa0m**2 * e2 * (2 + (1 + e2) * sa0) / (e12 * sa02_)  # == B + A
                dAB = 2 * e2 * (2 - e2 * (1 + sa02)) / (e12 * sa02_**2 * sca02)
                u_du = fsum_(s1_qZ *  g,  -D,  g * BA) \
                     / fsum_(s1_qZ * dg, -dD, dg * BA, g * dAB)  # == u/du
                ta0, d = Ta0.fsum2_(-u_du * (sca0 * sca02))
                if abs(d) < tol:
                    break
            else:
                raise AlbersError(iteration=_NUMIT0, txt=_no_convergence_fmt_ % (tol,))

        self._txi0  = txi0 = self._txif(ta0)
        self._scxi0 =        hypot1(txi0)
        self._sxi0  = sxi0 = txi0 / self._scxi0
        self._m02   = m02  = 1.0 / (1.0 + (b_a * ta0)**2)
        self._n0    = n0   = ta0 / hypot1(ta0)
        if polar:
            self._polar = True
            self._nrho0 = self._m0 = 0.0
        else:
            self._m0    = sqrt(m02)  # == nrho0 / E.a
            self._nrho0 = E.a * self._m0  # == E.a * sqrt(m02)
        self._k0_(1.0 if par1 else (k * sqrt(C / (m02 + n0 * qZ * sxi0))))
        self._lat0 = _Lat_(self._sign * degrees(atan(ta0)), name=_lat0_)

    def _s1_qZ_C2(self, ca1, sa1, ta1, ca2, sa2, ta2):
        '''(INTERNAL) Compute C{sm1 / (s / qZ)} and C{C} for .__init__.
        '''
        E = self.datum.ellipsoid
        b_a = E.b_a
        e2  = E.e2

        tb1   = b_a * ta1
        tb2   = b_a * ta2
        dtb12 = b_a * (tb1 + tb2)
        scb12 = 1 + tb1**2
        scb22 = 1 + tb2**2

        es1  = 1 - e2 * sa1**2
        es2  = 1 - e2 * sa2**2
        es12 = 1 + e2 * sa1 * sa2

        dsn = _Dsn(ta2, ta1, sa2, sa1)
        axi, bxi, sxi = self._a_b_sxi3((ca1, sa1, ta1, scb12),
                                       (ca2, sa2, ta2, scb22))

        dsxi = (es12 / (es2 * es1) + self._Datanhee(sa2, sa1)) * dsn / (2 * self._qx)
        C = fsum_(sxi * dtb12 / dsxi, scb22, scb12) / (2 * scb22 * scb12)

        sa12 = fsum_(sa1, sa2, sa1 * sa2)
        axi *= (1 + e2 * sa12) / (1 + sa12)
        bxi *= e2 * fsum_(sa1, sa2, es12) / (es1 * es2) + E.e12 * self._D2atanhee(sa1, sa2)
        s1_qZ = dsn * (axi * self._qZ - bxi) / (2 * dtb12)
        return s1_qZ, C

    def _a_b_sxi3(self, *ca_sa_ta_scb):
        '''(INTERNAL) Sum of C{sm1} terms and C{sin(xi)}s for ._s1_qZ_C2.
        '''
        a = b = s = 0
        for ca, sa, ta, scb in ca_sa_ta_scb:
            cxi, sxi, _ = self._cstxif3(ta)
            if sa > 0:
                sa += 1
                a  += (cxi / ca)**2 * sa / (1 + sxi)
                b  += scb * ca**2 / sa
            else:
                sa = 1 - sa
                a += (1 - sxi) / sa
                b += scb * sa
            s += sxi
        return a, b, s

    @property_RO
    def datum(self):
        '''Get the datum (L{Datum}).
        '''
        return self._datum

    @property_RO
    def equatoradius(self):
        '''Get the geodesic's equatorial (major) radius, semi-axis (C{meter}).
        '''
        return self.datum.ellipsoid.a

    majoradius = equatoradius  # for compatibility

    @property_RO
    def iteration(self):
        '''Get the iteration number (C{int}).
        '''
        return self._iteration

    @property_RO
    def flattening(self):
        '''Get the geodesic's flattening (C{float}).
        '''
        return self.datum.ellipsoid.f

    def forward(self, lat, lon, lon0=0, name=NN):
        '''Convert a geodetic location to east- and northing.

           @arg lat: Latitude of the location (C{degrees}).
           @arg lon: Longitude of the location (C{degrees}).
           @kwarg lon0: Optional central meridian longitude (C{degrees}).
           @kwarg name: Optional name for the location (C{str}).

           @return: An L{Albers7Tuple}C{(x, y, lat, lon, gamma, scale, datum)}.

           @note: The origin latitude is returned by C{property lat0}.  No
                  false easting or northing is added.  The value of B{C{lat}}
                  should be in the range C{[-90..90] degrees}.  The returned
                  values C{x} and C{y} will be large but finite for points
                  projecting to infinity, i.e. one or both of the poles.
        '''
        E = self.datum.ellipsoid
        s = self._sign

        k0    = self._k0
        n0    = self._n0
        nrho0 = self._nrho0
        txi0  = self._txi0

        sa, ca = sincos2d(_Lat_(lat) * s)
        ca = max(_EPSX, ca)
        ta = sa / ca

        _, sxi, txi = self._cstxif3(ta)
        dq = self._qZ * _Dsn(txi, txi0, sxi, self._sxi0) * (txi - txi0)
        drho = -E.a * dq / (sqrt(self._m02 - n0 * dq) + self._m0)

        lon = _Lon_(lon)
        if lon0:
            lon, _ = _diff182(_Lon_(lon0, name=_lon0_), lon)
        b = radians(lon)

        th = self._k02n0 * b
        sth, cth = sincos2(th)  # XXX sin, cos
        if n0:
            x = sth / n0
            y = (1 - cth if cth < 0 else sth**2 / (1 + cth)) / n0
        else:
            x = self._k02 * b
            y = 0
        t = nrho0 + n0 * drho
        x = t * x / k0
        y = s * (nrho0 * y - drho * cth) / k0

        g = degrees360(s * th)
        if t:
            k0 *= t * hypot1(E.b_a * ta) / E.a
        t = Albers7Tuple(x, y, lat, lon, g, k0, self.datum)
        return _xnamed(t, name or self.name)

    @property_RO
    def ispolar(self):
        '''Is this projection polar (c{bool})?
        '''
        return self._polar

    @property_RO
    def lat0(self):
        '''Get the latitude of the projection origin (C{degrees}).

           This is the latitude of minimum azimuthal scale and
           equals the B{C{lat}} in the 1-parallel L{AlbersEqualArea}
           and lies between B{C{lat1}} and B{C{lat2}} for the
           2-parallel L{AlbersEqualArea2} and L{AlbersEqualArea4}
           projections.
        '''
        return self._lat0

    @property_RO
    def lat1(self):
        '''Get the latitude of the first parallel (C{degrees}).
        '''
        return self._lat1

    @property_RO
    def lat2(self):
        '''Get the latitude of the second parallel (C{degrees}).

           @note: The second and first parallel latitudes are the
                  same instance for 1-parallel C{AlbersEqualArea*}
                  projections.
        '''
        return self._lat2

    def rescale0(self, lat, k=1.0):
        '''Set the azimuthal scale for this projection.

           @arg lat: Northern latitude (C{degrees}).
           @arg k: Azimuthal scale at latitude B{C{lat}} (C{scalar}).

           @raise AlbersError: Invalid B{C{lat}} or B{C{k}}.

           @note: This allows a I{latitude of conformality} to be specified.
        '''
        self._k0_(_Ks(k, 'k') / self.forward(lat, 0).scale)

    def reverse(self, x, y, lon0=0, name=NN, LatLon=None, **LatLon_kwds):
        '''Convert an east- and northing location to geodetic lat- and longitude.

           @arg x: Easting of the location (C{meter}).
           @arg y: Northing of the location (C{meter}).
           @kwarg lon0: Optional central meridian longitude (C{degrees}).
           @kwarg name: Optional name for the location (C{str}).
           @kwarg LatLon: Class to use (C{LatLon}) or C{None}.
           @kwarg LatLon_kwds: Optional, additional B{C{LatLon}} keyword
                               arguments, ignored if B{C{LatLon=None}}.

           @return: The geodetic (C{LatLon}) or if B{C{LatLon}} is C{None} an
                    L{Albers7Tuple}C{(x, y, lat, lon, gamma, scale, datum)}.

           @note: The origin latitude is returned by C{property lat0}.  No
                  false easting or northing is added.  The returned value of
                  C{lon} is in the range C{[-180..180] degrees} and C{lat}
                  is in the range C{[-90..90] degrees}.  If the given
                  B{C{x}} or B{C{y}} point is outside the valid projected
                  space the nearest pole is returned.
        '''
        x = Scalar(x, name=_x_)
        y = Scalar(y, name=_y_)
        E = self.datum.ellipsoid

        k0    = self._k0
        n0    = self._n0
        k0n0  = self._k0n0
        nrho0 = self._nrho0
        txi0  = self._txi0

        y_ = self._sign * y
        nx = k0n0 * x
        ny = k0n0 * y_
        y1 = nrho0 - ny

        drho = den = nrho0 + hypot(nx, y1)  # 0 implies origin with polar aspect
        if den:
            drho = fsum_(x * nx, -2 * y_ * nrho0, y_ * ny) * k0 / den
        # dsxia = scxi0 * dsxi
        dsxia = -self._scxi0 * (2 * nrho0 + n0 * drho) * drho / self._qZa2
        t = 1 - dsxia * (2 * txi0 + dsxia)
        txi = (txi0 + dsxia) / (sqrt(t) if t > _EPSX2 else _EPSX)

        ta = self._tanf(txi)
        lat = degrees(atan(ta * self._sign))

        b = atan2(nx, y1)
        lon = degrees(b / self._k02n0 if n0 else x / (y1 * k0))
        if lon0:
            lon += _norm180(_Lon_(lon0, name=_lon0_))
        lon = _norm180(lon)

        if LatLon is None:
            g = degrees360(self._sign * b)
            if den:
                k0 *= (nrho0 + n0 * drho) * hypot1(E.b_a * ta) / E.a
            r = Albers7Tuple(x, y, lat, lon, g, k0, self.datum)
        else:
            kwds = _xkwds(LatLon_kwds, datum=self.datum)
            r = LatLon(lat, lon, **kwds)
        return _xnamed(r, name or self.name)

    @property_RO
    def scale0(self):
        '''Get the central scale for the projection (C{float}).

           This is the azimuthal scale on the latitude of origin
           of the projection, see C{property lat0}.
        '''
        return self._k0

    def _atanhee(self, x):
        '''(INTERNAL) Function M{atanhee(x)}, defined as ...
           atanh(      E.e   * x) /       E.e   if f > 0  # oblate
           atan (sqrt(-E.e2) * x) / sqrt(-E.e2) if f < 0  # prolate
           x                                    if f = 0.
        '''
        E = self.datum.ellipsoid
        if E.f > 0 :  # oblate
            x = atanh(x * E.e) / E.e
        elif E.f < 0:  # prolate
            x = atan2(abs(x) * E.e, -1 if x < 0 else 1) / E.e
        return x

    def _atanhx1(self, x):
        '''(INTERNAL) Function M{atanh(sqrt(x)) / sqrt(x) - 1}.
        '''
        s = abs(x)
        if s < 0.5:  # for typical ...
            # x < E.e^2 = 2 * E.f use ...
            # x / 3 + x^2 / 5 + x^3 / 7 + ...
            y, k = x, 3
            S = Fsum(y / k)
            for _ in range(_TERMS):
                y *= x  # x**n
                k += 2  # 2*n + 1
                s, d = S.fsum2_(y / k)
                if not d:
                    break
        else:
            s = sqrt(s)
            s = (atanh(s) if x > 0 else atan(s)) / s - 1
        return s

    def _cstxif3(self, ta):
        '''(INTERNAL) Get 3-tuple C{(cos, sin, tan)} of M{xi(ta)}.
        '''
        t = self._txif(ta)
        c = 1 / hypot1(t)
        s = c * t
        return c, s, t

    def _Datanhee(self, x, y):
        '''(INTERNAL) Function M{Datanhee(x, y)}, defined as
           M{atanhee((x - y) / (1 - E.e^2 * x * y)) / (x - y)}.
        '''
        E = self.datum.ellipsoid
        d = 1 - E.e2 * x * y
        t = x - y
        if t:
            s = self._atanhee(t / d) / t
        elif d:
            s = 1 / d
        else:
            raise AlbersError(x=x, y=y, d=d, txt=_AlbersBase._Datanhee.__name__)
        return s

    def _D2atanhee(self, x, y):
        '''(INTERNAL) Function M{D2atanhee(x, y)}, defined as
           M{(Datanhee(1, y) - Datanhee(1, x)) / (y - x)}.
        '''
        e2 = self.datum.ellipsoid.e2

        if (abs(x) + abs(y)) * e2 < 0.5:
            e = k = z = 1
            C = Fsum()
            S = Fsum()
            T = Fsum()  # Taylor expansion
            for _ in range(_TERMS):
                T *= y; p = T.fsum_(z); z *= x  # PYCHOK ;
                T *= y; t = T.fsum_(z); z *= x  # PYCHOK ;
                e *= e2
                k += 2
                s, d = S.fsum2_(e * C.fsum_(p, t) / k)
                if not d:
                    break
        elif (1 - x):
            s = (self._Datanhee(1, y) - self._Datanhee(x, y)) / (1 - x)
        else:
            raise AlbersError(x=x, y=y, txt=_AlbersBase._D2atanhee.__name__)
        return s

    def _k0_(self, k):
        '''(INTERNAL) Set C{._k0}, C{._k02}, etc.
        '''
        self._k0    = k  = _Ks(k, 'k0')
        self._k02   = k2 =  k**2
        self._k0n0  = k  * self._n0
        self._k02n0 = k2 * self._n0

    def _tanf(self, txi):
        '''(INTERNAL) Function M{tan(xi)}.
        '''
        tol = _tol(_TOL, txi)

        e2 = self.datum.ellipsoid.e2
        qx = self._qx

        ta = txi
        Ta = Fsum(ta)
        for self._iteration in range(1, _NUMIT):  # max 2, mean 1.99
            # dtxi/dta = (scxi / sca)^3 * 2 * (1 - e^2) / (qZ * (1 - e^2 * sa^2)^2)
            ta2  = ta**2
            sca2 = 1 + ta2
            txia = self._txif(ta)
            s3qx = sqrt3(sca2 / (1 + txia**2)) * qx
            ta, d = Ta.fsum2_((txi - txia) * s3qx * (1 - e2 * ta2 / sca2)**2)
            if abs(d) < tol:
                return ta
        raise AlbersError(iteration=_NUMIT, txt=_no_convergence_fmt_ % (tol,))

    def _txif(self, ta):
        '''(INTERNAL) Function M{tan(a)}.
        '''
        E = self.datum.ellipsoid

        ca2 = 1 / (1 + ta**2)
        sa  = sqrt(ca2) * abs(ta)  # enforce odd parity

        es1    = sa * E.e2
        es2m1  = 1 - sa * es1
        sp1    = 1 + sa
        es1p1  = sp1 / (1 + es1)
        es1m1  = sp1 * (1 - es1)
        es2m1a = es2m1 * E.e12  # e2m
        s = sqrt((ca2 / (es1p1 * es2m1a) + self._atanhee(ca2 / es1m1)) *
                        (es1m1 / es2m1a  + self._atanhee(es1p1)))
        t = (sa / es2m1 + self._atanhee(sa)) / s
        if ta < 0:
            t = -t
        return t


class AlbersEqualArea(_AlbersBase):
    '''An Albers-equal-area projection with a single standard parallel.

       @see: L{AlbersEqualArea4} and L{AlbersEqualArea}.
    '''
    def __init__(self, lat, k0=1, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualArea} projection.

           @arg lat: Standard parallel (C{degrees}).
           @kwarg k0: Azimuthal scale on the standard parallel (C{scalar}).
           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).

           @raise AlbertError: Invalid B{C{lat}}, B{C{k0}} or no convergence.
        '''
        self._lat1 = self._lat2 = lat = _Lat_(lat, name=_lat1_)
        args = tuple(sincos2d(lat)) * 2 + (_Ks(k0, 'k0'), datum, name)
        _AlbersBase.__init__(self, *args)


class AlbersEqualArea2(_AlbersBase):
    '''An Albers-equal-area projection with two standard parallels.

       @see: L{AlbersEqualArea4} and L{AlbersEqualArea}.
    '''
    def __init__(self, lat1, lat2, k1=1, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualArea2} projection.

           @arg lat1: First standard parallel (C{degrees}).
           @arg lat2: Second standard parallel (C{degrees}).
           @kwarg k1: Azimuthal scale on the standard parallels (C{scalar}).
           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).

           @raise AlbertError: Invalid B{C{lat1}}m B{C{lat2}}, B{C{k1}}
                               or no convergence.
        '''
        self._lat1, self._lat2 = lats = _Lat_(lat1, name=_lat1_), \
                                        _Lat_(lat2, name=_lat2_)
        args = tuple(sincos2d(*lats)) + (_Ks(k1, 'k1'), datum, name)
        _AlbersBase.__init__(self, *args)


class AlbersEqualArea4(_AlbersBase):
    '''An Albers-equal-area projection specified by the C{sin} and C{cos}
       of both standard parallels.

       @see: L{AlbersEqualArea2} and L{AlbersEqualArea}.
    '''
    def __init__(self, slat1, clat1, slat2, clat2, k1=1, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualArea4} projection.

           @arg slat1: Sine of first standard parallel (C{scalar}).
           @arg clat1: Cosine of first standard parallel (non-negative C{scalar}).
           @arg slat2: Sine of second standard parallel (C{scalar}).
           @arg clat2: Cosine of second standard parallel (non-negative C{scalar}).
           @kwarg k1: Azimuthal scale on the standard parallels (C{scalar}).
           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).

           @raise AlbertError: Negative B{C{clat1}} or B{C{clat2}}, B{C{slat1}}
                               and B{C{slat2}} have opposite signs (hemispheres),
                               invalid B{C{k1}} or no convergence.
        '''
        def _Lat_s_c3(s, c, name):
            L = _Lat_(atan2d(s, c), name=name)
            r = 1.0 / Float_(hypot(s, c), Error=AlbersError, name=name)
            return L, s * r, c * r

        self._lat1, sa1, ca1 = _Lat_s_c3(slat1, clat1, _lat1_)
        self._lat2, sa2, ca2 = _Lat_s_c3(slat2, clat2, _lat2_)
        _AlbersBase.__init__(self, sa1, ca1, sa2, ca2, _Ks(k1, 'k1'), datum, name)


class AlbersEqualAreaCylindrical(_AlbersBase):
    '''An L{AlbersEqualArea} projection at C{lat=0} and C{k0=1} degenerating
       to the cylindrical-equal-area projection.
    '''
    _lat1 = _lat2 = _Lat_(0, name=_lat1_)

    def __init__(self, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualAreaCylindrical} projection.

           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).
        '''
        _AlbersBase.__init__(self, 0.0, 1.0, 0.0, 1.0, 1.0, datum, name)


class AlbersEqualAreaNorth(_AlbersBase):
    '''An L{AlbersEqualArea} projection at C{lat=90} and C{k0=1} degenerating
       to the L{azimuthal} L{LambertEqualArea} projection.
    '''
    _lat1 = _lat2 = _Lat_(90, name=_lat1_)

    def __init__(self, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualAreaNorth} projection.

           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).
        '''
        _AlbersBase.__init__(self, 1.0, 0.0, 1.0, 0.0, 1.0, datum, name)


class AlbersEqualAreaSouth(_AlbersBase):
    '''An L{AlbersEqualArea} projection at C{lat=-90} and C{k0=1} degenerating
       to the L{azimuthal} L{LambertEqualArea} projection.
    '''
    _lat1 = _lat2 = _Lat_(-90, name=_lat1_)

    def __init__(self, datum=Datums.WGS84, name=NN):
        '''New L{AlbersEqualAreaSouth} projection.

           @kwarg datum: Optional datum (C{Datum}).
           @kwarg name: Optional name for the projection (C{str}).
        '''
        _AlbersBase.__init__(self, -1.0, 0.0, -1.0, 0.0, 1.0, datum, name)


class Albers7Tuple(_NamedTuple):
    '''7-Tuple C{(x, y, lat, lon, gamma, scale, datum)}, in C{meter},
       C{meter}, C{degrees90}, C{degrees180}, C{degrees360}, C{float} and
       C{Datum} where C{(x, y)} is the projected, C{(lat, lon)} the geodetic
       location, C{gamma} the meridian convergence at point, the bearing of
       the y-axis measured clockwise from true North and C{scale} is the
       azimuthal scale of the projection at point.  The radial scale is
       the reciprocal C{1 / scale}.
    '''
    _Names_ = (_x_, _y_, _lat_, _lon_, _gamma_, _scale_, _datum_)

    def __new__(cls, x, y, lat, lon, g, k, datum):
        return _NamedTuple.__new__(cls, Scalar(x, name=_x_, Error=AlbersError),
                                        Scalar(y, name=_y_, Error=AlbersError),
                                        _Lat_(lat), _Lon_(lon),
                                        Degrees(g, name=_gamma_, Error=AlbersError),
                                        _Ks(k, _scale_), datum)


__all__ += _ALL_DOCS(Albers7Tuple, _AlbersBase)

# **) MIT License
#
# Copyright (C) 2016-2020 -- mrJean1 at Gmail -- All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.