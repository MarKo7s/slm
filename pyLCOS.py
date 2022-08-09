import fullscreenqt
import numpy as np
import numexpr as ne
import time
#ne.set_num_threads(16) # I am not useing large set of arrays so 8 seems the best

import sys
sys.path.append("C:\LAB\Coding\Python\MODULES")
import mark_lib as mkl


class LCOS(fullscreenqt.FullscreenWindow):
    def __init__(self, screen = 1, pixel_size = 9.2e-6, aperture_diameter = 7.5e-3, mask_size = (960,960), MODELAB_COMPATIBILITY = True, **kwargs):
        """_summary_

        Args:
            screen (int, optional): index of the monitor to be used to display the FULL MASKS. Defaults to 1.
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
        super().__init__(screen = screen) #This innit the screen, from now we
        
        self.screen_data = self.getBuffer() #(Y,X,RGB)
        self.LCOSsize = self.screen_data.shape[0:2]
        self.pixel_size  = pixel_size
        self.aperture_diameter = aperture_diameter
        self.masksize = mask_size
        #INIT OBJECT MEM SPACE
        att_period = 16
        self.attenuationPattern = self.binarycheckboard(self.masksize[0],self.masksize[1], spatial_frequency = 1/att_period,scale = 1, offset= True, pol='HV') #using HV to get the whole mask
        self.LCOS_array_H = np.zeros(self.LCOSsize,np.float32) #See performance with floats64
        self.LCOS_array_V = np. copy(self.LCOS_array_H)
        self.LCOS_array = np.copy(self.LCOS_array_H)
        
        
        
        #Init parameters - User can prove them through **kwarg - It takes phase masks already angle()
        zernikeH = np.zeros(mask_size,np.float64)
        zernikeV = np.zeros(mask_size,np.float64)
        patternH = np.zeros(mask_size,np.float64)
        patternV = np.zeros(mask_size,np.float64)     
        #masks parameters --> This is used before displaying the mask on the LCOS
        HmaskCenter = [self.LCOSsize[1]//4, self.LCOSsize[0]//2,] #Default center for H in X,Y coordinates
        VmaskCenter = [3*self.LCOSsize[1]//4, self.LCOSsize[0]//2] #Default center for V
        
        #This are the avaliable kwargs. If they are not provided defaulted to above value
        INITPARAMETERS = {'zernikeH': zernikeH, 'zernikeV': zernikeV, 'patternH': patternH, 'patternV': patternV, 'HmaskCenter': HmaskCenter,
                     'VmaskCenter': VmaskCenter, 'polEnabled': 'HV', 'zernikesEnabled': 1, 'patternEnabled': 1} 
        
        for arg in kwargs:
            INITPARAMETERS[arg] = kwargs[arg] #INIT with user specs
        
        Hmask_specs = {'zernike':INITPARAMETERS['zernikeH'], 'pattern': INITPARAMETERS['patternH'], 'att_enabled':0, 'attWeight': 0, 'centers': INITPARAMETERS['HmaskCenter']}
        Vmask_specs = {'zernike':INITPARAMETERS['zernikeV'], 'pattern': INITPARAMETERS['patternV'], 'att_enabled':0, 'attWeight': 0, 'centers': INITPARAMETERS['VmaskCenter']} 
        
        ############# IMPORTANT ATRIBUTES - THEY CONTROL THE OBJECT #################################      
        self.mask_specs = {'H': Hmask_specs, 'V': Vmask_specs} #After the object is created, modifying the parameters in this dictionary and runing setmask will update the LCOS mask
        #Control flags to add the masks
        self.polEnabled = INITPARAMETERS['polEnabled']
        self.zernikesEnabled = INITPARAMETERS['zernikesEnabled']
        self.patternEnabled = INITPARAMETERS['patternEnabled']
        
        #ModeLab Centers compatibility
        self.ModeLab = MODELAB_COMPATIBILITY
        #This centers can be different to the ones provided if modelab compatibility = True
        self.Hcenter = None
        self.Vcenter = None
        
        
        #Some other extra corrections -> in define center and setmask
        self.offset_mask = 0
        self.offset_center = 0 #It seems that 1 pixel offset match better modelab... I do not why
        
        #Apertures masks
        self.ap_H = None
        self.ap_V = None
        self.ap = None
        self.defineCenters()
        self.calcApertures() #This method should be call each time, centers aperture diameter and pixel size changes
                    
        # Added masks 
        self.Hmask = None # Result of adding Hmask_specs
        self.Vmask = None 
        
        self.DisplayedPhaseMask = None #After processing the 2 independend masks HV with other parameters and centers
        self.apertureApplied = None # The aperture filter applied
        self.DisplayedLevelMask = None # Final mask from 0 to 255
        
        self.refreshfreq = 0
        
        #Call setmask()??
    
    @staticmethod
    def getAngle(cmplxarray):
        im = cmplxarray.imag
        re = cmplxarray.real
        cc = ne.evaluate('arctan2(im,re)')
        return(cc)
    
    def calcApertures(self):
        self.ap_H = self.aperture(self.aperture_diameter,self.Hcenter,self.LCOSsize,self.pixel_size)
        self.ap_V = self.aperture(self.aperture_diameter,self.Vcenter,self.LCOSsize,self.pixel_size)
        self.ap = np.logical_or(self.ap_H,self.ap_V)

    def defineCenters(self):
        cH = self.mask_specs['H']['centers']
        cV =  self.mask_specs['V']['centers'] 
        
        if self.ModeLab == True:
            #Convert to integer in case somebody used floats
            cH = list(map(int,cH))
            cV = list(map(int,cV))
        
            #offset correction to be modelab compatible
            #This is to invert the position of the origin of the first pixel at the Y-axis + 1 pixel
            cH[1] = self.LCOSsize[0] - (cH[1]+1)
            cV[1] =  self.LCOSsize[0] - (cV[1]+1)
            
            cV[0] -=1 #For any reason there is an offset in this pol mask on the x axis (only here) 
                        
        self.Hcenter = [cH[0] - self.offset_center, cH[1] - self.offset_center]
        self.Vcenter = [cV[0] - self.offset_center, cV[1] - self.offset_center]
    
            
    def setCenters(self, centerH, centerV): #[x,y] format
        self.mask_specs['H']['centers'] = centerH
        self.mask_specs['V']['centers'] = centerV
        self.defineCenters()
        self.calcApertures()
          
    def addMasks(self):
        
        #Around 20 ms to run this piece of code when all masks have information (if some masks are 0 gets faster)
        
        att_phi_H = self.CalcAttPhase(self.mask_specs['H']['attWeight'])
        att_phi_V = self.CalcAttPhase(self.mask_specs['V']['attWeight'])
                
        a = self.mask_specs['H']['zernike'] #This should come from -pi to pi
        a1 = self.zernikesEnabled

        b = self.mask_specs['H']['pattern']  #This shohould come as -pi to pi
        b1 =  self.patternEnabled
        
        c = self.attenuationPattern # array from -0.5 to -0.5
        c1 = self.mask_specs['H']['att_enabled'] * att_phi_H # attenuation weight should go from -attphi/2 to attphi/2 to avoid pistoning effect 
               
        d = self.mask_specs['V']['zernike']
        d1 =  self.zernikesEnabled
        
        e = self.mask_specs['V']['pattern']
        e1 = self.patternEnabled
        
        f = self.attenuationPattern 
        f1 = self.mask_specs['V']['att_enabled'] * att_phi_V
        
        #I could unwrap myself without using angle and exp by it seems fast enough - 20 ms aprox to add all masks - Vectorizing both masks in one, should help as well
        self.Hmask = self.getAngle(ne.evaluate('exp(1j*((a*a1) + (b*b1) + (c*c1)))')) #This wrap the phase from -pi to pi 
        self.Vmask = self.getAngle(ne.evaluate('exp(1j*((d*d1) + (e*e1) + (f*f1)))'))  
    
    #Around 5 ms for this piece of code
    def masksToLCOS(self, mask_h = 0 , mask_v = 0, pol='HV'):
           
        slmX = self.LCOSsize[1]
        slmY = self.LCOSsize[0]
        
        #masks only can be 1920//2 = 960 -- 960x960 (usefull area) -- If provided masks are bigger they will be cropped -- If they are smaller it will spit an error
        maxsize = slmX//2
        lim = maxsize // 2
        
        dH = self.masksize
        mask_centers_H = [dH[0]//2 - self.offset_mask , dH[1]//2 - self.offset_mask] #This is de mask itself not the center on the LCOS
        cH = self.Hcenter #This has extra offset correction and mofied centers if modelab compatibility is on
        self.LCOS_array_H[cH[1]-lim:cH[1]+lim, cH[0]-lim:cH[0]+lim ] = mask_h[mask_centers_H[1]-lim:mask_centers_H[1]+lim,mask_centers_H[0]-lim:mask_centers_H[0]+lim ] #Assign and crop if its bigger  
        
        dV = dH
        mask_centers_V = [dV[0]//2 - self.offset_mask , dV[1]//2 -self. offset_mask]
        cV = self.Vcenter
        self.LCOS_array_V[cV[1]-lim:cV[1]+lim, cV[0]-lim:cV[0]+lim ] = mask_v[mask_centers_V[1]-lim:mask_centers_V[1]+lim,mask_centers_V[0]-lim:mask_centers_V[0]+lim ] #Assign and crop if its bigger
        
        if pol == 'H':
            self.LCOS_array = self.LCOS_array_H * self.ap_H
            self.apertureApplied = self.ap_H
        elif pol =='V':
           self. LCOS_array = self.LCOS_array_V * self.ap_V
           self.apertureApplied = self.ap_V
        elif pol == 'HV':
           a = self.LCOS_array_H
           b = self.ap_H 
           c = self.LCOS_array_V
           d = self.ap_V
           self.LCOS_array = (ne.evaluate('((a*b + c*d))'))
           self.apertureApplied = self.ap  

    #To write into the LCOS
    def LCOS_Display(self, arr_data, ch = 0):
        self.screen_data[:,:,ch] = arr_data
        self.update()
    
    def LCOS_Clean(self):
        self.LCOS_Display(np.zeros(self.LCOSsize))
    
    #Takes new patterns in case you only want to update new patterns on top zernikes attenuation etc etc. Otherwise it will take self parameters and build the mask
    def setmask(self, Hpattern = 0 , Vpattern = 0, pol= None ):
        t1 = time.time()
        #t = mkl.times #use t.tic() t.toc() to measure time
        if Hpattern != 0:
           self.mask_specs['H']['pattern'] = Hpattern
        if Vpattern != 0:
            self.mask_specs['V']['pattern'] = Vpattern
        if pol != None:
            self.polEnabled = pol
            
        #print('Adding mask')
        #t.tic()
        self.addMasks() #Update the masks
        #t.toc()
        #print('Bulding LCOS mask')
        #t.tic()
        self.masksToLCOS(mask_h = self.Hmask , mask_v = self.Vmask, pol=self.polEnabled) #Using de added masks
        #t.toc()
        self.DisplayePhasedMask = self.LCOS_array
        #print('Level mask')
        #t.tic()
        LEVELMASK = self.phaseTolevel(self.LCOS_array, self.apertureApplied)
        #t.toc()
        self.DisplayedLevelMask = LEVELMASK
        #print('Displaying')
        #t.tic()
        self.LCOS_Display(LEVELMASK)
        etime = time.time() - t1
        self.refreshfreq = 1/etime
        #t.toc()
    
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
    def aperture(diameter,center, LCOS_size, px_size):
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
    from PyQt5.QtWidgets import *
    
    from pylab import *
    
    app = QApplication(sys.argv)
    
    LCOSobject = LCOS(screen=1, mask_size=(960,960))
    
    app.exec()