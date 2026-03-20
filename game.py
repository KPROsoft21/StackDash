#!/usr/bin/env python3
"""
PIXEL QUEST — A Platformer Adventure
Sprites: Kenney.nl (CC0) — kenney_pixel-platformer + kenney_platformer-characters
"""

import pygame, sys, os, math, random, struct, json
pygame.init()
pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

# ── Constants ─────────────────────────────────────────────────────────────────
SW, SH   = 1280, 720
TILE     = 54
FPS      = 60
GRAVITY  = 0.58
MAX_FALL = 20
JUMP_VEL = -15.0
WALK_SPD = 4.8
COYOTE   = 8
JMP_BUF  = 10

BASE      = os.path.dirname(os.path.abspath(__file__))
TILES_DIR = os.path.join(BASE, "assets", "pixel-platformer", "Tiles")
CHARS_DIR = os.path.join(BASE, "assets", "platformer-characters", "PNG")
BG_DIR    = os.path.join(TILES_DIR, "Backgrounds")
CHR_DIR   = os.path.join(TILES_DIR, "Characters")
SAVE_FILE = os.path.join(BASE, "save.json")

# ── Colors ─────────────────────────────────────────────────────────────────────
WHITE  = (255,255,255); BLACK  = (0,0,0);     GOLD   = (255,215,0)
RED    = (220,60,60);   GREEN  = (60,200,80); DARK   = (15,20,40)
HEART  = (220,50,60);   HEARTY = (80,40,40);  CYAN   = (80,220,255)

# ── Sound generation ──────────────────────────────────────────────────────────
def gen_sound(freq=440, dur=0.12, vol=0.35, decay=8.0, shape='sine'):
    sr, n = 22050, int(22050 * dur)
    data = []
    for i in range(n):
        t = i / sr
        env = math.exp(-decay * t)
        if shape == 'square':
            v = 1.0 if math.sin(2*math.pi*freq*t) > 0 else -1.0
        elif shape == 'noise':
            v = random.uniform(-1, 1)
        else:
            v = math.sin(2*math.pi*freq*t)
        data.append(max(-32768, min(32767, int(v * env * vol * 32767))))
    buf = struct.pack(f'<{n*2}h', *[v for v in data for _ in range(2)])
    return pygame.mixer.Sound(buffer=buf)

SFX = {}
def init_sfx():
    SFX['jump']  = gen_sound(380, 0.14, 0.4,  6)
    SFX['land']  = gen_sound(180, 0.06, 0.25, 22)
    SFX['coin']  = gen_sound(880, 0.09, 0.3,  14)
    SFX['stomp'] = gen_sound(220, 0.12, 0.4,  8,  'square')
    SFX['hit']   = gen_sound(110, 0.22, 0.5,  4,  'noise')
    SFX['die']   = gen_sound(80,  0.45, 0.5,  2,  'square')
    SFX['win']   = gen_sound(660, 0.35, 0.4,  1.5)
    SFX['beep']  = gen_sound(440, 0.1,  0.3,  10)

# ── Particles ─────────────────────────────────────────────────────────────────
class Particle:
    __slots__ = ('x','y','vx','vy','color','size','life','age','grav')
    def __init__(self, x, y, vx, vy, color, size=4, life=30, grav=0.18):
        self.x,self.y,self.vx,self.vy = x,y,vx,vy
        self.color,self.size,self.life,self.age,self.grav = color,size,life,0,grav
    def update(self):
        self.x += self.vx; self.y += self.vy
        self.vy += self.grav; self.vx *= 0.93; self.age += 1
    @property
    def alive(self): return self.age < self.life
    def draw(self, surf, ox, oy):
        a = 1 - self.age/self.life
        s = max(1, int(self.size * a))
        pygame.draw.circle(surf, self.color, (int(self.x-ox), int(self.y-oy)), s)

def burst(particles, x, y, color, n=10, spd=3.5):
    for _ in range(n):
        ang = random.uniform(0, 6.283)
        sp  = random.uniform(0.5, spd)
        particles.append(Particle(x, y, math.cos(ang)*sp, math.sin(ang)*sp - 1.5,
                                  color, random.randint(3,6), random.randint(20,40)))

def dust(particles, x, y):
    for _ in range(6):
        particles.append(Particle(x, y,
            random.uniform(-2,2), random.uniform(-2.5,-0.5),
            (210,200,170), random.randint(2,5), random.randint(15,28)))

def sparkle(particles, x, y):
    for _ in range(12):
        ang = random.uniform(0, 6.283)
        sp  = random.uniform(1, 4)
        particles.append(Particle(x, y, math.cos(ang)*sp, math.sin(ang)*sp - 2,
                                  GOLD, random.randint(3,7), random.randint(25,45), 0.1))

# ── Camera ────────────────────────────────────────────────────────────────────
class Camera:
    def __init__(self, lw, lh):
        self.x = self.y = 0.0
        self.lw, self.lh = lw, lh
        self.shake = 0.0
    def follow(self, tx, ty):
        self.x += (tx - SW*0.38 - self.x) * 0.10
        self.y += (ty - SH*0.58 - self.y) * 0.10
        self.x = max(0, min(self.x, self.lw - SW))
        self.y = max(0, min(self.y, self.lh - SH))
    def jolt(self, amt): self.shake = max(self.shake, amt)
    def offset(self):
        sx = random.uniform(-self.shake, self.shake) if self.shake > 0 else 0
        sy = random.uniform(-self.shake, self.shake) if self.shake > 0 else 0
        self.shake = max(0, self.shake - 0.6)
        return int(self.x + sx), int(self.y + sy)

# ── Tile Loading ──────────────────────────────────────────────────────────────
def lt(path, sz=(TILE, TILE)):
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.scale(img, sz)
    return None

def load_all_tiles():
    T = {}
    def tile(key, idx, subdir="", sz=(TILE,TILE)):
        path = os.path.join(TILES_DIR, subdir, f"tile_{idx:04d}.png")
        T[key] = lt(path, sz)

    # Grass platform L/M/R/single  (indices 21-23 from TMX analysis)
    tile('pl', 21); tile('pm', 22); tile('pr', 23); tile('ps', 21)
    # Stone ground body L/M/R      (indices 121-123)
    tile('gl', 121); tile('gm', 122); tile('gr', 123); tile('gf', 122)
    # Grass surface variants        (indices 0-3)
    tile('sl', 0); tile('sm', 1); tile('sr', 2); tile('ss', 3)
    # Decorative tiles
    tile('deco0', 16); tile('deco1', 17); tile('deco2', 18)
    # Coin (golden char tile)
    T['coin'] = lt(os.path.join(CHR_DIR, "tile_0011.png"), (34,34))
    T['coin2']= lt(os.path.join(CHR_DIR, "tile_0012.png"), (34,34))
    # Background sky tiles
    T['sky0'] = lt(os.path.join(BG_DIR, "tile_0000.png"), (TILE,TILE))
    T['sky1'] = lt(os.path.join(BG_DIR, "tile_0008.png"), (TILE,TILE))
    return T

# ── Tilemap ───────────────────────────────────────────────────────────────────
SOLID = set('#X')
PLAT  = set('-')

class TileMap:
    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.H = len(self.rows)
        self.W = max(len(r) for r in self.rows) if self.rows else 0
    def get(self, tx, ty):
        if 0 <= ty < self.H and 0 <= tx < len(self.rows[ty]):
            return self.rows[ty][tx]
        return ' '
    def set(self, tx, ty, ch):
        if 0 <= ty < self.H and 0 <= tx < len(self.rows[ty]):
            self.rows[ty][tx] = ch
    def is_solid(self, tx, ty): return self.get(tx, ty) in SOLID
    def is_platform(self, tx, ty): return self.get(tx, ty) in PLAT

# ── Player ────────────────────────────────────────────────────────────────────
PLAYER_W, PLAYER_H = 30, 52

class Player:
    ANIM_SPD = 7
    def __init__(self, x, y):
        self.x, self.y   = float(x), float(y)
        self.vx, self.vy = 0.0, 0.0
        self.on_ground   = False
        self.facing      = 1
        self.state       = 'idle'
        self.anim_t      = 0
        self.health      = 3
        self.inv         = 0
        self.coyote      = 0
        self.jbuf        = 0
        self.score       = 0
        self.dead        = False
        self.dead_t      = 0
        self.combo       = 0
        self.combo_t     = 0
        self.noclip      = False
        self._spr        = {}
        self._load()

    def _load(self):
        base = os.path.join(CHARS_DIR, "Adventurer", "Poses")
        for p in ('idle','walk1','walk2','jump','fall','hurt','skid','duck'):
            f = os.path.join(base, f"adventurer_{p}.png")
            if os.path.exists(f):
                self._spr[p] = pygame.image.load(f).convert_alpha()

    def rect(self):
        return pygame.Rect(int(self.x)-PLAYER_W//2, int(self.y)-PLAYER_H, PLAYER_W, PLAYER_H)

    def _sprite(self):
        s = self.state
        if s == 'walk':
            k = ['walk1','walk2'][int(self.anim_t // self.ANIM_SPD) % 2]
            return self._spr.get(k)
        return self._spr.get(s)

    def update(self, keys, tm, moving_plats, particles, sfx):
        if self.dead:
            self.dead_t += 1; return

        left  = keys[pygame.K_LEFT]  or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        up    = keys[pygame.K_UP]    or keys[pygame.K_w]
        down  = keys[pygame.K_DOWN]  or keys[pygame.K_s]

        # ── NOCLIP mode ──────────────────────────────────────────────────────
        if self.noclip:
            spd = WALK_SPD * 2.5
            self.vx = (-spd if left else spd if right else 0)
            self.vy = (-spd if up   else spd if down  else 0)
            self.x += self.vx; self.y += self.vy
            self.facing = -1 if self.vx < 0 else (1 if self.vx > 0 else self.facing)
            self.state = 'walk' if self.vx != 0 else 'idle'
            self.anim_t += 1
            self.on_ground = False
            self.inv = max(self.inv - 1, 0)
            return
        # ─────────────────────────────────────────────────────────────────────

        if left:  self.vx = -WALK_SPD; self.facing = -1
        elif right: self.vx =  WALK_SPD; self.facing =  1
        else:
            self.vx *= 0.72
            if abs(self.vx) < 0.15: self.vx = 0.0

        # Combo decay
        if self.combo_t > 0:
            self.combo_t -= 1
            if self.combo_t == 0: self.combo = 0

        # Coyote + jump buffer
        if self.on_ground: self.coyote = COYOTE
        elif self.coyote > 0: self.coyote -= 1
        if self.jbuf > 0: self.jbuf -= 1

        if self.jbuf > 0 and self.coyote > 0:
            self.vy = JUMP_VEL
            self.coyote = self.jbuf = 0
            if 'jump' in sfx: sfx['jump'].play()
            dust(particles, self.x, self.y)

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        if self.inv > 0: self.inv -= 1

        # Move X
        self.x += self.vx
        self._collide_x(tm)

        # Moving platforms
        for mp in moving_plats:
            self._ride_mp(mp)

        # Move Y
        self.y += self.vy
        self.on_ground = False
        self._collide_y(tm, particles, sfx)
        # Check moving platform tops
        for mp in moving_plats:
            self._collide_mp(mp)

        # Animation state — after collision so on_ground is current
        if not self.on_ground:
            self.state = 'jump' if self.vy < 0 else 'fall'
            self.anim_t += 1
        elif abs(self.vx) > 0.4:
            self.state = 'walk'
            self.anim_t += 1
        else:
            self.state = 'idle'
            # don't reset anim_t — walk resumes from same frame

    def _collide_x(self, tm):
        r = self.rect()
        for tx in range(r.left//TILE, (r.right+TILE-1)//TILE):
            for ty in range(r.top//TILE, (r.bottom+TILE-1)//TILE):
                if tm.is_solid(tx, ty):
                    tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if r.colliderect(tr):
                        if self.vx > 0: self.x = tr.left - PLAYER_W//2 - 0.1
                        else:           self.x = tr.right + PLAYER_W//2 + 0.1
                        self.vx = 0; r = self.rect()

    def _collide_y(self, tm, particles, sfx):
        r = self.rect()
        for tx in range(r.left//TILE, (r.right+TILE-1)//TILE):
            for ty in range(r.top//TILE, (r.bottom+TILE-1)//TILE):
                ch = tm.get(tx, ty)
                if ch in SOLID:
                    tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if r.colliderect(tr):
                        if self.vy >= 0:
                            if not self.on_ground:
                                dust(particles, self.x, self.y)
                                if 'land' in sfx: sfx['land'].play()
                            self.y = float(tr.top); self.on_ground = True
                        else: self.y = float(tr.bottom + PLAYER_H)
                        self.vy = 0; r = self.rect()
                elif ch in PLAT:
                    tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE//3)
                    if r.colliderect(tr) and self.vy > 0 and r.bottom - self.vy <= tr.top + 4:
                        if not self.on_ground:
                            dust(particles, self.x, self.y)
                            if 'land' in sfx: sfx['land'].play()
                        self.y = float(tr.top); self.on_ground = True; self.vy = 0
                        r = self.rect()

    def _ride_mp(self, mp):
        pass  # simplified: moving platform pushes player

    def _collide_mp(self, mp):
        r  = self.rect()
        tr = pygame.Rect(int(mp.x), int(mp.y), mp.w, TILE//3)
        if r.colliderect(tr) and self.vy >= 0 and r.bottom - self.vy <= tr.top + 6:
            self.y = float(tr.top); self.on_ground = True; self.vy = 0
            self.x += mp.vx

    def hurt(self, particles, cam, sfx):
        if self.inv > 0: return
        self.health -= 1
        self.inv = 100
        self.vy  = -9
        if 'hit' in sfx: sfx['hit'].play()
        cam.jolt(9)
        burst(particles, self.x, self.y-26, (220,60,60), 14, 4)
        if self.health <= 0:
            self.dead = True
            if 'die' in sfx: sfx['die'].play()

    def bounce_stomp(self):
        self.vy = -13
        self.combo += 1
        self.combo_t = 90

    def draw(self, surf, ox, oy):
        spr = self._sprite()
        if spr is None: return
        if self.inv > 0 and (self.inv//5)%2 == 1: return
        if self.facing == -1:
            spr = pygame.transform.flip(spr, True, False)
        sw, sh = spr.get_size()
        surf.blit(spr, (int(self.x-ox)-sw//2, int(self.y-oy)-sh))
        # Combo text
        if self.combo >= 2 and self.combo_t > 0:
            f = pygame.font.SysFont('Arial',20,bold=True)
            ct = f.render(f"x{self.combo} COMBO!", True, GOLD)
            surf.blit(ct, (int(self.x-ox)-ct.get_width()//2, int(self.y-oy)-90))
        # Noclip indicator — ghost trail dots
        if self.noclip:
            f = pygame.font.SysFont('Arial',14,bold=True)
            gt = f.render("👻 GHOST MODE", True, (180,120,255))
            surf.blit(gt, (int(self.x-ox)-gt.get_width()//2, int(self.y-oy)-72))

# ── Enemy ─────────────────────────────────────────────────────────────────────
ENEMY_W, ENEMY_H = 28, 50

class Enemy:
    SPEED    = 1.7
    ANIM_SPD = 9
    def __init__(self, x, y, pl, pr):
        self.x, self.y     = float(x), float(y)
        self.vx            = self.SPEED
        self.vy            = 0.0
        self.pl, self.pr   = float(pl), float(pr)
        self.facing        = 1
        self.on_ground     = False
        self.dead          = False
        self.dead_t        = 0
        self.anim_t        = 0
        self._spr          = {}
        self._load()

    def _load(self):
        base = os.path.join(CHARS_DIR, "Zombie", "Poses")
        for p in ('idle','walk1','walk2','hurt'):
            f = os.path.join(base, f"zombie_{p}.png")
            if os.path.exists(f):
                self._spr[p] = pygame.image.load(f).convert_alpha()

    def rect(self):
        return pygame.Rect(int(self.x)-ENEMY_W//2, int(self.y)-ENEMY_H, ENEMY_W, ENEMY_H)

    def update(self, tm, particles):
        if self.dead:
            self.dead_t += 1; return

        self.x += self.vx
        if self.x <= self.pl: self.x = self.pl; self.vx =  self.SPEED; self.facing = 1
        if self.x >= self.pr: self.x = self.pr; self.vx = -self.SPEED; self.facing = -1

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.y += self.vy
        self.on_ground = False
        r = self.rect()
        for tx in range(r.left//TILE, (r.right+TILE-1)//TILE):
            for ty in range(r.top//TILE, (r.bottom+TILE-1)//TILE):
                if tm.is_solid(tx, ty) or tm.is_platform(tx, ty):
                    tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if tm.is_platform(tx, ty):
                        tr = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE//3)
                    if r.colliderect(tr):
                        if self.vy >= 0: self.y = float(tr.top); self.on_ground=True; self.vy=0
                        else:            self.y = float(tr.bottom+ENEMY_H);          self.vy=0
                        r = self.rect()
        self.anim_t += 1

    def stomp(self, particles):
        self.dead = True
        burst(particles, self.x, self.y-25, (80,200,80), 14, 4)

    def draw(self, surf, ox, oy):
        if self.dead:
            if self.dead_t < 15:
                r = self.rect().move(-ox, -oy)
                s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                s.fill((255,80,80,max(0, 200 - self.dead_t*14)))
                surf.blit(s, r)
            return
        k = ['walk1','walk2'][int(self.anim_t//self.ANIM_SPD)%2]
        spr = self._spr.get(k) or self._spr.get('idle')
        if spr is None: return
        if self.facing == -1: spr = pygame.transform.flip(spr,True,False)
        sw,sh = spr.get_size()
        surf.blit(spr, (int(self.x-ox)-sw//2, int(self.y-oy)-sh))

# ── Coin ──────────────────────────────────────────────────────────────────────
class Coin:
    def __init__(self, x, y, frames):
        self.x, self.y = x, y
        self.frames    = frames
        self.bob       = random.uniform(0, 6.28)
        self.anim_t    = random.randint(0, 20)
        self.collected = False
        self.collect_t = 0

    def rect(self):
        return pygame.Rect(self.x-14, self.y-14, 28, 28)

    def update(self):
        self.bob    += 0.05
        self.anim_t += 1
        if self.collected: self.collect_t += 1

    def draw(self, surf, ox, oy):
        if self.collected:
            if self.collect_t < 20:
                a   = 1 - self.collect_t/20
                spr = self.frames[0] if self.frames else None
                if spr:
                    s = spr.copy()
                    s.set_alpha(int(255*a))
                    by = math.sin(self.bob)*4 - self.collect_t*2
                    surf.blit(s, (int(self.x-ox)-s.get_width()//2, int(self.y+by-oy)-s.get_height()//2))
            return
        by = math.sin(self.bob)*4
        fr = self.frames[int(self.anim_t//12)%len(self.frames)] if self.frames else None
        if fr:
            surf.blit(fr, (int(self.x-ox)-fr.get_width()//2, int(self.y+by-oy)-fr.get_height()//2))
        else:
            pygame.draw.circle(surf, GOLD, (int(self.x-ox), int(self.y+by-oy)), 10)
            pygame.draw.circle(surf, (255,240,120), (int(self.x-ox)-2, int(self.y+by-oy)-2), 5)

# ── Flag ──────────────────────────────────────────────────────────────────────
class Flag:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.t = 0.0

    def rect(self):
        return pygame.Rect(self.x-14, self.y-TILE*2, 36, TILE*2)

    def update(self): self.t += 0.05

    def draw(self, surf, ox, oy):
        px, py = int(self.x-ox), int(self.y-oy)
        # Pole shadow
        pygame.draw.rect(surf, (80,60,20), (px-1, py-TILE*2+2, 5, TILE*2))
        # Pole
        pygame.draw.rect(surf, (200,160,80), (px-2, py-TILE*2, 5, TILE*2))
        # Flag wave
        w = math.sin(self.t)*7
        pts = [(px+3,py-TILE*2),(px+36+w,py-TILE*2+12),(px+3,py-TILE*2+24)]
        pygame.draw.polygon(surf, GREEN, pts)
        pygame.draw.polygon(surf, (30,160,50), pts, 2)
        # Star on flag
        cx = px + 20 + w//2
        cy = py - TILE*2 + 12
        for i in range(5):
            a = math.pi/2 + i*math.pi*2/5
            b = math.pi/2 + (i+0.5)*math.pi*2/5
            p1 = (cx + math.cos(a)*7, cy - math.sin(a)*7)
            p2 = (cx + math.cos(b)*3, cy - math.sin(b)*3)
        # simpler star
        pygame.draw.circle(surf, GOLD, (cx, cy), 5)

# ── Moving Platform ───────────────────────────────────────────────────────────
class MovingPlatform:
    def __init__(self, x, y, w, x1, x2, speed=1.8, tiles=None):
        self.x,self.y = float(x),float(y)
        self.w        = w * TILE
        self.x1,self.x2 = float(x1),float(x2)
        self.vx       = speed
        self.tiles    = tiles  # (plat_l, plat_m, plat_r)

    def update(self):
        self.x += self.vx
        if self.x <= self.x1 or self.x >= self.x2:
            self.vx = -self.vx
            self.x  = max(self.x1, min(self.x, self.x2))

    def draw(self, surf, ox, oy):
        n = self.w // TILE
        for i in range(n):
            sx = int(self.x-ox) + i*TILE
            sy = int(self.y-oy)
            if self.tiles:
                pl,pm,pr = self.tiles
                t = pl if i==0 else (pr if i==n-1 else pm)
                if t: surf.blit(t, (sx,sy))
            else:
                pygame.draw.rect(surf, (60,180,80), (sx,sy,TILE,TILE//3))

# ── Level Data ────────────────────────────────────────────────────────────────
# Map chars: ' '=air, '#'=solid ground (auto-tiles), 'X'=ground fill,
#            '-'=platform, '$'=coin, 'E'=enemy, '@'=spawn, 'F'=flag

def _L(rows): return [r for r in rows]

# Level builder helper: takes ground row ('_' = solid column, ' ' = gap)
# and returns all map rows with matching gaps in fill rows
def _build_level(sky_rows, ground_str, fill_rows=3):
    """
    ground_str uses:  '#'=surface, 'X'=fill surface, ' '=gap
    Platform/entity rows are in sky_rows.
    Fill rows below ground automatically match gaps.
    """
    g = list(ground_str)
    fill_str = ''.join('X' if c in '#X' else ' ' for c in g)
    rows = list(sky_rows) + [ground_str] + [fill_str]*fill_rows
    return rows

LEVELS = [
  {
    "name": "VERDANT HILLS",
    "bg_top": (100,185,245), "bg_bot": (190,235,255),
    "map": _build_level([
      # col:  0    5    10   15   20   25   30   35   40   45   50   55   60   65
      "                                                                          ",#0
      "         $              $                    $               $            ",#1
      "       -----          -----               -------          -----          ",#2
      "                                $    $                              $     ",#3
      "               $             ----  ---           E              ------    ",#4
      "             -----                                                         ",#5
      "  @                  E                    E                           F   ",#6
    ],
    # ground row — gaps at cols 5-9, 14-16, 23-25, 32-34, 44-45, 62-63
    "#####     ######  ########     ########   #########     ############   #####",
    fill_rows=3,
    ),
    "moving_platforms": [],
  },
  {
    "name": "CRYSTAL CAVERNS",
    "bg_top": (30,50,90), "bg_bot": (60,90,140),
    "map": _build_level([
      "                                                                           ",#0
      "         $              $                    $          $                  ",#1
      "       ------          -----              ------      ------               ",#2
      "                                $                               $   ----  ",#3
      "    $           E    -------   ---   E               E                    ",#4
      "  -----                                                                    ",#5
      "  @                   E                    E    E                      F  ",#6
    ],
    "####     #######   ########     #######    ####    ########    ##############",
    fill_rows=3,
    ),
    "moving_platforms": [
      (18, 5, 3, 18*TILE, 28*TILE, 2.0),
      (42, 4, 3, 38*TILE, 50*TILE, 2.5),
    ],
  },
  {
    "name": "ZOMBIE PEAK",
    "bg_top": (50,25,80), "bg_bot": (110,65,150),
    "map": _build_level([
      "                                                                           ",#0
      "       $       $           $    $       $      $              $            ",#1
      "     -----    ----       -----  ---   ----    -----         ------         ",#2
      "                    $                                   $                  ",#3
      "            E     -----      E           E           ----       E          ",#4
      "   $                               $                                  $   ",#5
      "  ---    E           E         E        E    E           E        F       ",#6
    ],
    "####   ######   ########   ######   ######    ######   ################   ##",
    fill_rows=3,
    ),
    "moving_platforms": [
      (14, 4, 3, 11*TILE, 23*TILE, 2.2),
      (34, 3, 3, 29*TILE, 41*TILE, 2.8),
      (52, 4, 2, 48*TILE, 60*TILE, 3.2),
    ],
  },
]

# ── Tile renderer helper ──────────────────────────────────────────────────────
def get_tile_surf(T, tm, tx, ty):
    ch = tm.get(tx, ty)
    if ch not in ('#','X','-'): return None

    above = tm.get(tx, ty-1)
    left  = tm.get(tx-1, ty)
    right = tm.get(tx+1, ty)
    is_surface = above not in ('#','X','-')
    has_left   = left  in ('#','X')
    has_right  = right in ('#','X')

    if ch == '-':
        if   not has_left and not has_right: return T.get('ss') or T.get('pm')
        elif not has_left:                   return T.get('pl')
        elif not has_right:                  return T.get('pr')
        else:                                return T.get('pm')

    # '#' or 'X'
    if is_surface and ch == '#':
        if   not has_left and not has_right: return T.get('ss')
        elif not has_left:                   return T.get('sl')
        elif not has_right:                  return T.get('sr')
        else:                                return T.get('sm')
    else:
        if   not has_left:  return T.get('gl')
        elif not has_right: return T.get('gr')
        else:               return T.get('gm')

# ── Background drawing ────────────────────────────────────────────────────────
_cloud_cache = None
def make_cloud_surf():
    s = pygame.Surface((110,50), pygame.SRCALPHA)
    pygame.draw.ellipse(s,(255,255,255,210),(0,20,60,30))
    pygame.draw.ellipse(s,(255,255,255,200),(25,8,70,35))
    pygame.draw.ellipse(s,(255,255,255,210),(50,20,60,30))
    return s

CLOUDS = [(i*170+random.randint(0,80), random.randint(40,200)) for i in range(14)]

def draw_bg(surf, top, bot, cam_x):
    global _cloud_cache
    # Gradient sky
    for y in range(SH):
        t = y/SH
        r = int(top[0]*(1-t)+bot[0]*t)
        g = int(top[1]*(1-t)+bot[1]*t)
        b = int(top[2]*(1-t)+bot[2]*t)
        pygame.draw.line(surf,(r,g,b),(0,y),(SW,y))
    # Parallax hills
    hill_x = int(-cam_x * 0.15) % SW
    for hx in range(-SW, SW*2, 200):
        hh = 120
        pts = []
        for dx in range(0, 210, 10):
            pts.append((hx+hill_x+dx, SH - hh + int(math.sin(dx*0.04)*40)))
        pts += [(hx+hill_x+200, SH), (hx+hill_x, SH)]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (max(0,top[0]-20),min(255,top[1]+15),max(0,top[2]-30)), pts)
    # Clouds
    if _cloud_cache is None:
        _cloud_cache = make_cloud_surf()
    for cx,cy in CLOUDS:
        x = (cx - int(cam_x*0.25)) % (SW+200) - 100
        surf.blit(_cloud_cache, (x, cy))

# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_heart(surf, cx, cy, r, color):
    pygame.draw.circle(surf, color, (cx-r//2, cy), r//2)
    pygame.draw.circle(surf, color, (cx+r//2, cy), r//2)
    pygame.draw.polygon(surf, color, [(cx-r,cy),(cx,cy+r+2),(cx+r,cy)])

def draw_hud(surf, player, lvl_idx, total_coins, got_coins, fonts):
    fbig, fmed, fsml = fonts
    # Hearts
    for i in range(3):
        col = HEART if i < player.health else HEARTY
        draw_heart(surf, 22+i*38, 28, 13, col)
        draw_heart(surf, 22+i*38, 28, 13, (0,0,0) if col==HEARTY else (255,120,120))
        draw_heart(surf, 22+i*38, 28, 13, col)
    # Score
    sc = fbig.render(f"SCORE  {player.score:06d}", True, WHITE)
    sh = fbig.render(f"SCORE  {player.score:06d}", True, (0,0,0))
    surf.blit(sh, (SW-sc.get_width()-18, 18))
    surf.blit(sc, (SW-sc.get_width()-20, 16))
    # Level name
    ln = fmed.render(f"LEVEL {lvl_idx+1}  {LEVELS[lvl_idx]['name']}", True, (220,240,255))
    surf.blit(ln, (SW//2-ln.get_width()//2, 16))
    # Coins
    ct = fsml.render(f"COINS  {got_coins}/{total_coins}", True, GOLD)
    surf.blit(ct, (18, 56))

# ── Game ──────────────────────────────────────────────────────────────────────
MENU='menu'; PLAY='play'; LDONE='ldone'; GOVER='gover'; WIN='win'

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SW, SH))
        pygame.display.set_caption("PIXEL QUEST")
        self.clock  = pygame.time.Clock()
        self.fonts  = (
            pygame.font.SysFont('Arial',26,bold=True),
            pygame.font.SysFont('Arial',20,bold=True),
            pygame.font.SysFont('Arial',15),
        )
        self.ftitle = pygame.font.SysFont('Arial',72,bold=True)
        self.fmid   = pygame.font.SysFont('Arial',30,bold=True)
        self.T      = load_all_tiles()
        init_sfx()

        self.state    = MENU
        self.lvl_idx  = 0
        self.hi_score = self._load_hi()
        self.menu_t   = 0.0

        # per-level objects (set in load_level)
        self.player    = None
        self.tm        = None
        self.enemies   = []
        self.coins     = []
        self.flag      = None
        self.mplats    = []
        self.particles = []
        self.camera    = None
        self.bg_top    = (100,185,245)
        self.bg_bot    = (190,235,255)
        self.total_coins = 0
        self.ldone_t   = 0
        self.gover_t   = 0

    # ── persistence ──────────────────────────────────────────────────────────
    def _load_hi(self):
        try:
            with open(SAVE_FILE) as f: return json.load(f).get('hi',0)
        except: return 0
    def _save_hi(self, score):
        if score > self.hi_score:
            self.hi_score = score
            try:
                with open(SAVE_FILE,'w') as f: json.dump({'hi':score},f)
            except: pass

    # ── level loading ─────────────────────────────────────────────────────────
    def load_level(self, idx):
        ld = LEVELS[idx]
        rows = ld["map"]
        self.tm = TileMap(rows)
        self.enemies   = []
        self.coins     = []
        self.flag      = None
        self.mplats    = []
        self.particles = []
        self.total_coins = 0
        spawn = None

        coin_frames = [f for f in [self.T.get('coin'), self.T.get('coin2')] if f]

        for ty, row in enumerate(rows):
            for tx, ch in enumerate(row):
                cx = tx*TILE + TILE//2
                cy = (ty+1)*TILE
                if ch == '@':
                    spawn = (cx, (ty+1)*TILE)  # feet at bottom of '@' tile
                    self.tm.set(tx, ty, ' ')
                elif ch == 'F':
                    self.flag = Flag(cx, cy)
                    self.tm.set(tx, ty, ' ')
                elif ch == '$':
                    self.coins.append(Coin(cx, cy - TILE//2, coin_frames))
                    self.total_coins += 1
                    self.tm.set(tx, ty, ' ')
                elif ch == 'E':
                    pl = cx - TILE*4
                    pr = cx + TILE*4
                    self.enemies.append(Enemy(cx, (ty+1)*TILE, pl, pr))
                    self.tm.set(tx, ty, ' ')

        if spawn:
            self.player = Player(spawn[0], spawn[1])
        else:
            self.player = Player(TILE*2, self.tm.H*TILE - TILE*5)

        lw = self.tm.W * TILE
        lh = self.tm.H * TILE
        self.camera = Camera(lw, lh)
        self.camera.x = self.player.x - SW*0.38
        self.camera.y = self.player.y - SH*0.58
        self.bg_top = ld["bg_top"]
        self.bg_bot = ld["bg_bot"]

        # Moving platforms
        plat_tiles = (self.T.get('pl'), self.T.get('pm'), self.T.get('pr'))
        for spec in ld.get("moving_platforms",[]):
            tx2,ty2,w,x1,x2,spd = spec
            self.mplats.append(MovingPlatform(tx2*TILE, ty2*TILE, w, x1, x2, spd, plat_tiles))

        self.ldone_t = 0
        self.gover_t = 0

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN:
                    self._keydown(ev.key)

            if   self.state == MENU:  self._upd_menu();  self._draw_menu()
            elif self.state == PLAY:  self._upd_play();  self._draw_play()
            elif self.state == LDONE: self._upd_ldone(); self._draw_ldone()
            elif self.state == GOVER: self._upd_gover(); self._draw_gover()
            elif self.state == WIN:   self._upd_win();   self._draw_win()

            pygame.display.flip()

    # ── key handling ──────────────────────────────────────────────────────────
    def _keydown(self, k):
        if self.state == MENU:
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.lvl_idx = 0; self.load_level(0); self.state = PLAY
        elif self.state == PLAY:
            if k in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                if self.player and not self.player.dead:
                    self.player.jbuf = JMP_BUF
            if k == pygame.K_g and self.player:
                self.player.noclip = not self.player.noclip
                self.player.vy = 0  # kill momentum on toggle
            if k == pygame.K_ESCAPE: self.state = MENU
        elif self.state == LDONE:
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                nxt = self.lvl_idx + 1
                if nxt < len(LEVELS):
                    p_score = self.player.score if self.player else 0
                    self.lvl_idx = nxt; self.load_level(nxt)
                    self.player.score = p_score  # carry score
                    self.state = PLAY
                else:
                    self.state = WIN
        elif self.state in (GOVER, WIN):
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = MENU

    # ── menu ──────────────────────────────────────────────────────────────────
    def _upd_menu(self): self.menu_t += 0.025

    def _draw_menu(self):
        s = self.screen
        for y in range(SH):
            t = y/SH
            off = math.sin(self.menu_t + t*3)*18
            r = max(0,min(255,int(60+off+t*50)))
            g = max(0,min(255,int(100+off*0.4+t*40)))
            b = max(0,min(255,int(190+off*0.2)))
            pygame.draw.line(s,(r,g,b),(0,y),(SW,y))

        bob = math.sin(self.menu_t*2)*8
        title = self.ftitle.render("PIXEL QUEST", True, WHITE)
        shadow= self.ftitle.render("PIXEL QUEST", True, (0,80,160))
        cx = SW//2
        ty = SH//4
        s.blit(shadow,(cx-title.get_width()//2+5, ty+5+bob))
        s.blit(title, (cx-title.get_width()//2,   ty+bob))

        sub = self.fmid.render("A Platformer Adventure", True, (200,230,255))
        s.blit(sub,(cx-sub.get_width()//2, ty+90+bob))

        pulse = int(200+55*math.sin(self.menu_t*4))
        inst  = self.fmid.render("PRESS SPACE TO START", True,(pulse,pulse,0))
        s.blit(inst,(cx-inst.get_width()//2, SH*2//3))

        f = self.fonts[2]
        for i,line in enumerate([
            "Arrow Keys / WASD  ·  Move",
            "Space / W / Up  ·  Jump",
            "Land on enemies to stomp them!",
            "Reach the flag to complete the level",
        ]):
            t2 = f.render(line, True, (170,210,240))
            s.blit(t2,(cx-t2.get_width()//2, SH*3//4+i*22))

        hi = self.fonts[2].render(f"HI-SCORE: {self.hi_score:06d}", True, GOLD)
        s.blit(hi,(cx-hi.get_width()//2, SH-44))
        cr = self.fonts[2].render("Sprites: Kenney.nl (CC0)", True,(120,150,180))
        s.blit(cr,(SW-cr.get_width()-10, SH-22))

    # ── play update ───────────────────────────────────────────────────────────
    def _upd_play(self):
        if not self.player: return
        keys = pygame.key.get_pressed()

        if not self.player.dead:
            self.player.update(keys, self.tm, self.mplats, self.particles, SFX)
        else:
            self.player.dead_t += 1
            if self.player.dead_t > 80:
                self._save_hi(self.player.score)
                self.state = GOVER
                return

        for e in self.enemies:   e.update(self.tm, self.particles)
        for c in self.coins:     c.update()
        for mp in self.mplats:   mp.update()
        if self.flag:            self.flag.update()

        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles: p.update()

        self._check_enemies()
        self._check_coins()

        if self.player.y > self.tm.H*TILE + 120 and not self.player.dead:
            self.player.hurt(self.particles, self.camera, SFX)
            if not self.player.dead:
                # respawn at start
                self.player.x = TILE*2; self.player.y = (self.tm.H-4)*TILE
                self.player.vx = self.player.vy = 0

        if self.flag and not self.player.dead:
            if self.player.rect().colliderect(self.flag.rect()):
                SFX.get('win') and SFX['win'].play()
                burst(self.particles, self.player.x, self.player.y-30, GOLD, 20, 5)
                self._save_hi(self.player.score)
                self.state = LDONE

        self.camera.follow(self.player.x, self.player.y)

    def _check_enemies(self):
        if self.player.dead or self.player.inv > 0: return
        pr = self.player.rect()
        for e in self.enemies:
            if e.dead: continue
            er = e.rect()
            if pr.colliderect(er):
                if self.player.vy > 1 and pr.bottom <= er.centery + 18:
                    e.stomp(self.particles)
                    bonus = 100 * (self.player.combo + 1)
                    self.player.score += bonus
                    self.player.bounce_stomp()
                    SFX.get('stomp') and SFX['stomp'].play()
                    # score popup
                    burst(self.particles, e.x, e.y-30, GOLD, 8, 2)
                else:
                    self.player.hurt(self.particles, self.camera, SFX)

    def _check_coins(self):
        if self.player.dead: return
        pr = self.player.rect()
        for c in self.coins:
            if c.collected: continue
            if pr.colliderect(c.rect()):
                c.collected = True
                self.player.score += 50
                sparkle(self.particles, c.x, c.y)
                SFX.get('coin') and SFX['coin'].play()

    # ── play draw ─────────────────────────────────────────────────────────────
    def _draw_play(self):
        s   = self.screen
        ox, oy = self.camera.offset()

        draw_bg(s, self.bg_top, self.bg_bot, ox)
        self._draw_tiles(ox, oy)
        for mp in self.mplats:   mp.draw(s, ox, oy)
        for c in self.coins:     c.draw(s, ox, oy)
        if self.flag:            self.flag.draw(s, ox, oy)
        for e in self.enemies:   e.draw(s, ox, oy)
        if self.player:          self.player.draw(s, ox, oy)
        for p in self.particles: p.draw(s, ox, oy)

        got = sum(1 for c in self.coins if c.collected)
        draw_hud(s, self.player, self.lvl_idx, self.total_coins, got, self.fonts)
        if self.player and self.player.noclip:
            f = self.fonts[1]
            txt = f.render("[ G ] GHOST MODE ON", True, (180,120,255))
            s.blit(txt, (SW//2 - txt.get_width()//2, SH - 36))

    def _draw_tiles(self, ox, oy):
        tm = self.tm
        tx0 = max(0, ox//TILE);         tx1 = min(tm.W, (ox+SW)//TILE+2)
        ty0 = max(0, oy//TILE);         ty1 = min(tm.H, (oy+SH)//TILE+2)
        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                t = get_tile_surf(self.T, tm, tx, ty)
                if t:
                    s = tx*TILE-ox; y = ty*TILE-oy
                    self.screen.blit(t,(s,y))

    # ── level done ────────────────────────────────────────────────────────────
    def _upd_ldone(self):
        self.ldone_t += 1
        if self.ldone_t % 8 == 0:
            burst(self.particles, random.randint(100,SW-100), random.randint(100,SH-200),
                  random.choice([GOLD,GREEN,WHITE,CYAN]), 8, 5)
        for p in self.particles: p.update()
        self.particles = [p for p in self.particles if p.alive]

    def _draw_ldone(self):
        s  = self.screen
        ox,oy = self.camera.offset()
        draw_bg(s, self.bg_top, self.bg_bot, ox)
        self._draw_tiles(ox,oy)
        if self.player: self.player.draw(s,ox,oy)
        for p in self.particles: p.draw(s,ox,oy)

        ov = pygame.Surface((SW,SH), pygame.SRCALPHA)
        ov.fill((0,0,0,160)); s.blit(ov,(0,0))

        t1 = self.ftitle.render("LEVEL COMPLETE!", True, GOLD)
        shadow = self.ftitle.render("LEVEL COMPLETE!", True,(100,60,0))
        cx = SW//2
        bob = math.sin(self.ldone_t*0.1)*5
        s.blit(shadow,(cx-t1.get_width()//2+4, SH//3+4+bob))
        s.blit(t1,    (cx-t1.get_width()//2,   SH//3+bob))

        sc = self.fmid.render(f"Score: {self.player.score if self.player else 0:06d}", True, WHITE)
        s.blit(sc,(cx-sc.get_width()//2, SH//3+100))

        got = sum(1 for c in self.coins if c.collected)
        cc = self.fmid.render(f"Coins: {got}/{self.total_coins}", True, GOLD)
        s.blit(cc,(cx-cc.get_width()//2, SH//3+140))

        blink = self.ldone_t//18 % 2 == 0
        if blink:
            nxt = "PRESS SPACE — NEXT LEVEL" if self.lvl_idx+1<len(LEVELS) else "PRESS SPACE — FINALE!"
            t2 = self.fmid.render(nxt, True, (200,255,200))
            s.blit(t2,(cx-t2.get_width()//2, SH*2//3))

    # ── game over ─────────────────────────────────────────────────────────────
    def _upd_gover(self):
        self.gover_t += 1

    def _draw_gover(self):
        s = self.screen
        for y in range(SH):
            t=y/SH; d=self.gover_t/60
            r=max(0,min(255,int(80-40*t+d*20)))
            g=max(0,min(255,int(10-5*t)))
            b=max(0,min(255,int(20-10*t)))
            pygame.draw.line(s,(r,g,b),(0,y),(SW,y))

        cx = SW//2
        t1 = self.ftitle.render("GAME OVER", True, RED)
        sh = self.ftitle.render("GAME OVER", True,(80,0,0))
        s.blit(sh,(cx-t1.get_width()//2+4, SH//3+4))
        s.blit(t1,(cx-t1.get_width()//2,   SH//3))

        sc = self.fmid.render(f"Score: {self.player.score if self.player else 0:06d}", True, WHITE)
        s.blit(sc,(cx-sc.get_width()//2, SH//3+100))
        hi = self.fmid.render(f"Hi-Score: {self.hi_score:06d}", True, GOLD)
        s.blit(hi,(cx-hi.get_width()//2, SH//3+140))

        blink = self.gover_t//20%2==0
        if blink:
            t2 = self.fmid.render("PRESS SPACE TO RETURN", True, (220,220,220))
            s.blit(t2,(cx-t2.get_width()//2, SH*2//3))

    # ── win ───────────────────────────────────────────────────────────────────
    def _upd_win(self): pass

    def _draw_win(self):
        s = self.screen
        for y in range(SH):
            t=y/SH
            pygame.draw.line(s,(int(20+t*40),int(10+t*30),int(60+t*80)),(0,y),(SW,y))

        cx = SW//2
        t1 = self.ftitle.render("YOU WIN!", True, GOLD)
        sh = self.ftitle.render("YOU WIN!", True,(100,70,0))
        s.blit(sh,(cx-t1.get_width()//2+4, SH//3+4))
        s.blit(t1,(cx-t1.get_width()//2,   SH//3))

        sc = self.fmid.render(f"Final Score: {self.player.score if self.player else 0:06d}", True, WHITE)
        s.blit(sc,(cx-sc.get_width()//2, SH//3+100))
        hi = self.fmid.render(f"Hi-Score: {self.hi_score:06d}", True, GOLD)
        s.blit(hi,(cx-hi.get_width()//2, SH//3+140))

        t2 = self.fmid.render("Thanks for playing!  SPACE to return", True,(200,255,200))
        s.blit(t2,(cx-t2.get_width()//2, SH*2//3))

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    Game().run()
