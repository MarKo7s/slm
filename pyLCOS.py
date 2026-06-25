import numpy as np
import numexpr as ne
import time
#ne.set_num_threads(16) # I am not useing large set of arrays so 8 seems the best

import sys
#sys.path.append("C:\LAB\Coding\Python\MODULES")
#import mark_lib as mkl

import pathlib
#I think this is not needed anymore since we are using the repo root
p = pathlib.Path(__file__).parent.parent
path_to_module = p
#print(path_to_module)
sys.path.append(str(path_to_module))

#If I do not do from folder.fullscreenqt import module, super(). will fail when LCOS called from other module -- I do not know what the F*** is happeing
from hdmi.fullscreenqt import FullscreenWindow
from utilities.read_specs import load_slm_specs
from utilities.displays import find_display, display_discovery
from maksSpecs import ModMuxMask

class LCOS(FullscreenWindow):
    def __init__(self, screen = 1, channel = 0, pixel_size = 9.2e-6, aperture_diameter = 7.5e-3, mask_size = (960,960), MODELAB_COMPATIBILITY = True,  **kwargs):
        """_summary_

        Args:
            screen (int, optional): index of the monitor to be used to display the FULL MASKS. Defaults to 1.
            channel (int, optional): channel to be used to display the mask (red, green, blue) as (0, 1, 2). Defaults to 0 (red).
            pixel_size (_type_, optional): pixel pitch of the SLM. Defaults to 9.2e-6.
            aperture_diameter (_type_, optional): Diemater of the aperture to used to crop the masks in m. Defaults to 7.5e-3.
            mask_size (tuple, optional): size of the independed mask provided (zernikes H and V, patterns ...). Defaults to (960,960).
            MODELAB_COMPATIBILITY (bool) : Use when using zernikes optimized in Modelab.
                                            It only affects to masks centers. It applies some offsets to the provided centers(modelab centers)
                                            to be able to center the mask at the same spot as in Modelab

            **kwargs: 
                zernike_H (array), zernike_V (array), pattern_H (array), pattern_V(array), HmaskCenter ([x,y]), VmaskCenter([x,y]), 
                polselect('H', 'V' or 'HV'), zernikesEnabled (0 or 1), patternEnabled (0 or 1)
        """

        #Auto detection based on the slm model
        if isinstance(screen, str):
            self.alias = screen
            screen = self._screen_autodetect(screen)
        else:
            self.alias = str(screen)

        self.display  = screen #use the index to connect
        super().__init__(screen = self.display) #This innit the screen
        
        self.screen_data = self.getBuffer() #(Y,X,RGB) --> From FullScreeWindow class
        self.ch = channel
        self.LCOSsize = self.screen_data.shape[0:2]
        self.pixel_size  = pixel_size
        self.aperture_diameter = aperture_diameter
        self.masksize = mask_size

        #Init attenuation pattern use
        att_period = 16
        self.attenuationPattern = self.binarycheckboard(self.masksize[0],self.masksize[1], spatial_frequency = 1/att_period,scale = 1, offset= True, pol='HV') #using HV to get the whole mask
    
        #Create the ModMuxMask object, holding the masks, center and the apertures
        self.ModMuxMask = ModMuxMask(aperture_diameter = aperture_diameter, LCOS_size = self.LCOSsize, px_size = pixel_size, mask_size = mask_size,
                                    ModelabCompatibility = MODELAB_COMPATIBILITY, offset_center = 0)
    
        
        #Init parameters from kwargs or defaults
        self._init_parameters(self.ModMuxMask, **kwargs) #populates the ModMuxMask object with the kwargs

        #Some other extra corrections -> in define center and setmask
        self.offset_mask = 0
                    
        # Added masks 
        self.Hmask = np.zeros(mask_size, np.float32) # Result of adding Hmask_specs
        self.Vmask = np.zeros(mask_size, np.float32) 
        #LCOS arrays
        self.LCOS_array_H = np.zeros(self.LCOSsize, np.float32) #See performance with floats64
        self.LCOS_array_V = np. copy(self.LCOS_array_H)
        self.LCOS_array = np.copy(self.LCOS_array_H)
        #Intermediated masks
        self.DisplayedPhaseMask = np.zeros(self.LCOSsize, np.float32) #After processing the 2 independend masks HV with other parameters and centers
        self.apertureApplied = np.zeros(self.LCOSsize, np.uint8) # The aperture filter applied
        self.DisplayedLevelMask = np.zeros(self.LCOSsize, np.uint8) # Final mask from 0 to 255
        
        self.refreshfreq = 0

        #Call setmask to display the masks
        self.setmask()
    
    def _init_parameters(self, mm: ModMuxMask, **kwargs):

        """Init the parameters from the kwargs.
        """
        #This are the avaliable kwargs. If they are not provided defaulted to above value
        INITPARAMETERS = {'zernikeH': None, 'zernikeV': None, 'patternH': None, 'patternV': None, 'HmaskCenter': None,
                     'VmaskCenter': None, 'polEnabled': 'HV', 'zernikesEnabled': 1, 'patternEnabled': 1} 
        #Fill custom diccionary with which provided by the user
        for arg in kwargs:
            try:
                #only if exist the init parameter fill it
                if arg in INITPARAMETERS:
                    INITPARAMETERS[arg] = kwargs[arg] #INIT with user specs
                else:
                    print(arg, "could not be initialized because it is not supported")
            except KeyError:
                print(arg, "could not be initialized")

        mm = self.ModMuxMask
        if INITPARAMETERS['zernikeH'] is not None:
            mm.H.zernike = INITPARAMETERS['zernikeH']
        if INITPARAMETERS['zernikeV'] is not None:
            mm.V.zernike = INITPARAMETERS['zernikeV']
        if INITPARAMETERS['patternH'] is not None:
            mm.H.pattern = INITPARAMETERS['patternH']
        if INITPARAMETERS['patternV'] is not None:
            mm.V.pattern = INITPARAMETERS['patternV']
        mm.pol = INITPARAMETERS['polEnabled']
        mm.H.zernikes_enabled = bool(INITPARAMETERS['zernikesEnabled'])
        mm.V.zernikes_enabled = bool(INITPARAMETERS['zernikesEnabled'])
        mm.H.pattern_enabled = bool(INITPARAMETERS['patternEnabled'])
        mm.V.pattern_enabled = bool(INITPARAMETERS['patternEnabled'])
        if INITPARAMETERS['HmaskCenter'] is not None and INITPARAMETERS['VmaskCenter'] is not None:
            mm.set_centers(INITPARAMETERS['HmaskCenter'], INITPARAMETERS['VmaskCenter'])

    def _screen_autodetect(self, screen):
        """Auto detect the screen to use.
        """
        slm_specs = load_slm_specs()
        connected_displays = display_discovery()
        target_screen = slm_specs.get(screen, None) #type: ignore
        if target_screen is not None:
            w,h = target_screen["resolution"]
            print(f'Target slm "{screen}" found with resolution {w}x{h}')
        else:
            raise ValueError(f"Screen {screen} not found in slm_specs.json")

        screen = find_display(connected_displays, w = w, h = h) #get the monitor index

        return screen
        
    #Around 20 ms to run this piece of code when all masks have information (if some masks are 0 gets faster)
    def _addMasks(self):
        """ Goes through all masks parameters and adds them together. It does it for H and V pols separately.
        """
        att_phi_H = self.CalcAttPhase(self.ModMuxMask.H.att_weight)
        att_phi_V = self.CalcAttPhase(self.ModMuxMask.V.att_weight)
        pi = np.pi
        
        #! Just referencing
        a = self.ModMuxMask.H.zernike #This should come from -pi to pi
        a1 = self.ModMuxMask.H.zernikes_enabled

        b = self.ModMuxMask.H.pattern  #This shohould come as -pi to pi
        b1 = self.ModMuxMask.H.pattern_enabled
        
        c = self.attenuationPattern # array from -0.5pi to 0.5pi for a total of pi phase attenuation
        c1 = self.ModMuxMask.H.att_enabled * att_phi_H # attenuation weight should go from -attphi/2 to attphi/2 to avoid pistoning effect 
        
        d = self.ModMuxMask.V.zernike
        d1 = self.ModMuxMask.V.zernikes_enabled
        
        e = self.ModMuxMask.V.pattern
        e1 = self.ModMuxMask.V.pattern_enabled
        
        f = self.attenuationPattern 
        f1 = self.ModMuxMask.V.att_enabled * att_phi_V
        
        #!Adding the phase of all masks
        ne.evaluate('(((a*a1 + b*b1 + c*c1) + pi) % (2*pi)) - pi', out=self.Hmask, global_dict={'pi': pi})
        ne.evaluate('(((d*d1 + e*e1 + f*f1) + pi) % (2*pi)) - pi', out=self.Vmask, global_dict={'pi': pi})
    
    #Around 5 ms for this piece of code
    def _masksToLCOS(self, mask_h = 0 , mask_v = 0, pol='HV'):
        """It put the indiviaul H and V masks on the LCOS array. It also applies the aperture filter.

        Args:
            mask_h (array): H mask
            mask_v (array): V mask
            pol (str): 'H', 'V' or 'HV'
        """

        slmX = self.LCOSsize[1]
        slmY = self.LCOSsize[0]
        
        #masks only can be 1920//2 = 960 -- 960x960 (usefull area) -- If provided masks are bigger they will be cropped -- If they are smaller it will spit an error
        maxsize = slmX//2
        lim = maxsize // 2
        
        dH = self.masksize
        mask_centers_H = [dH[0]//2 - self.offset_mask , dH[1]//2 - self.offset_mask] #This is de mask itself not the center on the LCOS
        cH = self.ModMuxMask.Hcenter #This has extra offset correction and mofied centers if modelab compatibility is on
        self.LCOS_array_H[cH[1]-lim:cH[1]+lim, cH[0]-lim:cH[0]+lim ] = mask_h[mask_centers_H[1]-lim:mask_centers_H[1]+lim,mask_centers_H[0]-lim:mask_centers_H[0]+lim ] #Assign and crop if its bigger  
        
        dV = dH
        mask_centers_V = [dV[0]//2 - self.offset_mask , dV[1]//2 -self. offset_mask]
        cV = self.ModMuxMask.Vcenter
        self.LCOS_array_V[cV[1]-lim:cV[1]+lim, cV[0]-lim:cV[0]+lim ] = mask_v[mask_centers_V[1]-lim:mask_centers_V[1]+lim,mask_centers_V[0]-lim:mask_centers_V[0]+lim ] #Assign and crop if its bigger

        #Reference assignation for simplicity
        a = self.LCOS_array_H
        b = self.ModMuxMask.ap_H 
        c = self.LCOS_array_V
        d = self.ModMuxMask.ap_V
   
        if pol == 'H':
            ne.evaluate('a*b', out = self.LCOS_array) #This is the same as self.LCOS_array = self.LCOS_array_H * self.ap_H
            self.apertureApplied[:] = self.ModMuxMask.ap_H
        elif pol =='V':
           ne.evaluate('c*d', out = self.LCOS_array) #This is the same as self.LCOS_array = self.LCOS_array_V * self.ap_V
           self.apertureApplied[:] = self.ModMuxMask.ap_V
        elif pol == 'HV':
           ne.evaluate('((a*b + c*d))', out = self.LCOS_array) # the aperture is applied at each pol already
           self.apertureApplied[:] = self.ModMuxMask.ap  

    def _update_centers(self):
        """Intermediate method to clean the LCOS array when centers are updated.
        """
        #When center are updated, we need to clean up the LCoS array
        self.LCOS_array_H.fill(0)
        self.LCOS_array_V.fill(0)
        self.LCOS_array.fill(0)

    def _display_masks(self):
        """Display the masks on the LCOS.
        """
        self._masksToLCOS(mask_h = self.Hmask , mask_v = self.Vmask, pol=self.ModMuxMask.pol) #Using de added masks
        self.DisplayedPhaseMask[:] = self.LCOS_array
        LEVELMASK = self.phaseTolevel(self.LCOS_array, self.apertureApplied)
        self.DisplayedLevelMask[:] = LEVELMASK
        self.LCOS_Display(LEVELMASK) #Display using the internal set channel

    def resetAttenuation(self):
        self.ModMuxMask.H.att_enabled = False
        self.ModMuxMask.H.att_weight = 0
        self.ModMuxMask.V.att_enabled = False
        self.ModMuxMask.V.att_weight = 0

    #! Modifying the centers from attributes will not update the apertures. Call this function to update the apertures.
    def setCenters(self, centerH, centerV, display = True):
        """Update the centers of the H and V masks and display masks on the LCOS.
        Args:
            centerH (list): Center of the H mask. As [x,y]
            centerV (list): Center of the V mask. As [x,y]
            display (bool): Whether to display the masks on the LCOS
        """
        self.ModMuxMask.set_centers(centerH, centerV) #Set center update internally apertures
        self._update_centers() #Update centers basically only clean the LCOS array since apertures are updated internally
        if display:
            self._display_masks() #display masks without updating the masks

        return self
        
    #Takes new patterns in case you only want to update new patterns on top zernikes attenuation etc etc. Otherwise it will take self parameters and build the mask
    def setmask(self, Hpattern = 0 , Vpattern = 0, pol= None ):
        """Functio to call when you want to update the masks and display them on the LCOS

        Args:
            Hpattern (int): H pattern
            Vpattern (int): V pattern
            pol (str): 'H', 'V' or 'HV'
        """

        t1 = time.time()

        if Hpattern != 0:
           self.ModMuxMask.H.pattern = Hpattern
        if Vpattern != 0:
            self.ModMuxMask.V.pattern = Vpattern
        if pol != None:
            self.ModMuxMask.pol = pol

        self._addMasks() #Gnerate the masks

        self._display_masks() #Display the masks on the LCOS
        etime = time.time() - t1
        self.refreshfreq = 1/etime

    #To write into the LCOS
    def LCOS_Display(self, arr_data, ch = None):
        if ch is None:
            ch = self.ch
        self.screen_data[: , :, ch] = arr_data
        self.update()
    
    def LCOS_Clean(self, ch = None):
        """ Clean the LCOS screen. If ch is None, clean all channels. If ch is provided, clean only the specified channel.
        """
        if ch is None:
            self.screen_data[: , :, :] *= 0
            self.DisplayedLevelMask[:] = 0
            self.DisplayedPhaseMask[:] = 0
        else:
            self.screen_data[: , :, ch] *= 0
            if ch == self.ch:
                self.DisplayedLevelMask[:] = 0
                self.DisplayedPhaseMask[:] = 0

        self.update()

    def set_channel(self, channel: int) -> None:
        """Switch RGB drive channel (0=red, 1=green, 2=blue). Clears the display first."""
        if channel not in (0, 1, 2):
            raise ValueError("channel must be 0, 1, or 2")
        self.LCOS_Clean()
        self.ch = channel

    #I got tired.. so I am passing for now
    def save(self): #Save settings. 
        pass
    def restore(self): #Restore from saved settings
        pass
    def load(self,**kwargs): #load from dictionary 
        pass
    
    #Auxialiar methods    
    @staticmethod
    def CalcAttPhase(att):
        att_linear = 10**(-att/10) #this is in linear
        att_phase = 2 * np.arccos(np.sqrt(att_linear)) # phase, from 0 to pi
        return(att_phase)    

    @staticmethod
    def getAngle(cmplxarray):
        im = cmplxarray.imag
        re = cmplxarray.real
        cc = ne.evaluate('arctan2(im,re)')
        return(cc)
        
    @staticmethod
    def binarycheckboard(width, height, spatial_frequency, scale=1, offset = False ,pol = 'HV'):
        y = np.arange(height, dtype = np.float64)#linspace(0,2*pi,1080)
        x = np.arange(width, dtype = np.float64)
        X,Y = np.meshgrid(x,y)
        
        GY = (((Y*spatial_frequency)%(1.0)>=.5)*scale).astype(np.float64)
        GX = (((X*spatial_frequency)%(1.0)>=.5)*scale).astype(np.float64)
        
        chBoard = abs(GX - GY)
        
        #if offset True, the pattern goes from -scale/2 to scale/2
        if offset == True:
            offset = scale/2
            chBoard -= offset
        
        if pol == 'H':
            chBoard[:,int(x.max()//2):-1] = 0
        elif pol == 'V':
            chBoard[:,0:int(x.max()//2)] = 0

        return(chBoard)
        
    #25 ms for this piece of code.
    @staticmethod
    def phaseTolevel(phasemask, aperture = 1): #phase mask to a level mask ready to send to the LCOS
        pi = np.pi
        operate = ne.evaluate('255*((phasemask+pi)/(2*pi))')
        operate_uint8 = operate.astype(np.uint8) # Lost of information since it will round to the smallest - as well it will wrap values ourside -pi and pi (This happen when HV mask superimpose and no phase wrap has been done)
        error = ne.evaluate('operate-operate_uint8')
        operate_uint8[error>0.5]+=1
        level_array = operate_uint8 * aperture
        return(level_array)
    
    #This is slow, no thought to recalculate apertures all the time
    @staticmethod
    def aperture(diameter, center, LCOS_size, px_size):
        pxY = LCOS_size[0]
        pxX = LCOS_size[1]
        x = np.arange(pxX) - center[0] 
        y = np.arange(pxY) - center[1] 
        X,Y = np.meshgrid(x,y)
        r = (np.sqrt(X**2 + Y**2))
        m = np.copy(X) * 0
        radius_px = np.floor(diameter/(2*px_size)) 
    
        m[r<=(radius_px)] = 1
        return(m)


if __name__ == '__main__':
    
    import sys
    from PySide6.QtWidgets import *
    
    from pylab import *
    
    app = QApplication(sys.argv)
    
    LCOSobject = LCOS(screen=1, mask_size=(960,960))
    
    app.exec()