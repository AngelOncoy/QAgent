// sidebar.js — barra lateral: navegación, secuencia de agentes y estado del sandbox
// HTML del componente (se monta en el marcador data-componente="sidebar/sidebar" de index.html)
registrarComponente('sidebar/sidebar', `<!-- ======================= SIDEBAR ======================= -->
<aside>
  <div class="brand">
    <div class="logo" role="img" aria-label="QAgent"></div>
    <div><b>QAgent</b><span class="ver">v2.4</span><small>Autonomous Test Engine</small></div>
  </div>

  <!-- Sidebar de inicio -->
  <div id="sideHome">
    <div class="navlbl">Inicio</div>
    <nav>
      <a class="on" data-h="welcome" onclick="go('welcome')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10H3z"/></svg>Proyectos</a>
      <a data-h="config" onclick="go('config')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/></svg>Configuración</a>
      <a><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h7v14H4zM13 5h7v14h-7z"/></svg>Guía de uso</a>
    </nav>
  </div>

  <!-- Sidebar de proyecto (réplica de tu diseño + 2 vistas nuevas) -->
  <div id="sideProj" class="hide">
    <div class="navlbl">Secuencia de agentes</div>
    <div class="seq">
      <div class="it"><svg class="lg" fill="none" height="18" viewBox="0 -.01 39.5 39.53" width="18" xmlns="http://www.w3.org/2000/svg"><title>Claude (Anthropic)</title><path d="m7.75 26.27 7.77-4.36.13-.38-.13-.21h-.38l-1.3-.08-4.44-.12-3.85-.16-3.73-.2-.94-.2-.88-1.16.09-.58.79-.53 1.13.1 2.5.17 3.75.26 2.72.16 4.03.42h.64l.09-.26-.22-.16-.17-.16-3.88-2.63-4.2-2.78-2.2-1.6-1.19-.81-.6-.76-.26-1.66 1.08-1.19 1.45.1.37.1 1.47 1.13 3.14 2.43 4.1 3.02.6.5.24-.17.03-.12-.27-.45-2.23-4.03-2.38-4.1-1.06-1.7-.28-1.02c-.1-.42-.17-.77-.17-1.2l1.23-1.67.68-.22 1.64.22.69.6 1.02 2.33 1.65 3.67 2.56 4.99.75 1.48.4 1.37.15.42h.26v-.24l.21-2.81.39-3.45.38-4.44.13-1.25.62-1.5 1.23-.81.96.46.79 1.13-.11.73-.47 3.05-.92 4.78-.6 3.2h.35l.4-.4 1.62-2.15 2.72-3.4 1.2-1.35 1.4-1.49.9-.71h1.7l1.25 1.86-.56 1.92-1.75 2.22-1.45 1.88-2.08 2.8-1.3 2.24.12.18.31-.03 4.7-1 2.54-.46 3.03-.52 1.37.64.15.65-.54 1.33-3.24.8-3.8.76-5.66 1.34-.07.05.08.1 2.55.24 1.09.06h2.67l4.97.37 1.3.86.78 1.05-.13.8-2 1.02-2.7-.64-6.3-1.5-2.16-.54h-.3v.18l1.8 1.76 3.3 2.98 4.13 3.84.21.95-.53.75-.56-.08-3.63-2.73-1.4-1.23-3.17-2.67h-.21v.28l.73 1.07 3.86 5.8.2 1.78-.28.58-1 .35-1.1-.2-2.26-3.17-2.33-3.57-1.88-3.2-.23.13-1.11 11.95-.52.61-1.2.46-1-.76-.53-1.23.53-2.43.64-3.17.52-2.52.47-3.13.28-1.04-.02-.07-.23.03-2.36 3.24-3.59 4.85-2.84 3.04-.68.27-1.18-.61.11-1.09.66-.97 3.93-5 2.37-3.1 1.53-1.79-.01-.26h-.09l-10.44 6.78-1.86.24-.8-.75.1-1.23.38-.4 3.14-2.16z" fill="#d97757"/></svg>1. Planner<span class="pill p-blue">AST / Specs</span></div>
      <div class="it"><img class="lg" width="18" height="18" alt="Xiaomi" title="Xiaomi" src="data:image/png;base64,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">2. Generator<span class="pill p-purple">PyTest Synth</span></div>
      <div class="it"><img class="lg" width="18" height="18" alt="ChatGPT (OpenAI)" title="ChatGPT (OpenAI)" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAUWElEQVR42u1de7SVZZn/vXvvwyEEDigeQUqWQDqDwaiJOkQNE5lgire8Li84NsWMC0tspjK8laMxU0vLMMOyNE2mbDJnZjFq0yBigKCOEqDmLZNRIS4q4oGz9/ebP/bzdp7znvd9v+/bl3MO6bfWWfty9nd7nud9Lr/n8hn04UayAMAYYyrqu4kApgI4GsAEAO8F0AZgoPxkF4DXAbwMYD2AlQAeMsasVccoAqAxJsG7m5fwRohkP48jeRnJVSQ7mH/rkH2/RHKsZgRJ8y7FuxNfE34SydtI7nQIWiFZltfEQ/DE+Y3edpL8AclDfOd8pxO/JK/DSF5PcpciXGeE4GmbZUin+u5tkv9Mcog+9zte8klOJ/lbRaiyh+iaoJ3yG/3XGWFY4jBiPcmp71gmaH1P8lJFsE4P8Vwpzrp1elSRZkQnyTnKLhTktRT4s79puv0wzSY+gIIxpkLyegCfA2A9k4L+qXxvdXUCYC2ARwGsA7ARwJtyvUPFMzoEwAcBfEAdpyLH1feVyGcD4GpjzFU12qzEGMM9jQElY0yZ5LcAzAVQFiIbh2j2Jp8BcDuAe4wx6zIyeBKAUwCcC+BAzzEtgysASgCuBnALgHHCyHYAg+WadgL4A4DfA3gBwEuOi7znuLfK4F4uamC3R3WU5fX3JD9D8j3uMRy1oNVG0fntEJKfJflqiqEmybcyqLVdJDeIR3U6yb0d97awJxjcEwP6XhPjhyT3dYheyGFfCtq4kjyA5J1CwEqAEdrV7fT8+fZ7heS3JVDsv+6tNV4k9ye5RW6mEiD+XIfwpp4Vp1bdcJLrnHP5mJDVtS2r73fLqhir77c/Sv/djpqxN2XdzjMbRPiCXTFyrIuVGkoyErnsBH6h4E97aNtJfq5frQbH13eJT3UDfyO/a6nTvdWqZybJNSlSnihip23lgKvsMuLfrQrtcyYo9fNrDwPs+xsaQHwNZ0wg+dMMgZ2P6JtEVa2Sv3UkXwswIxZnPENyQp8ywRpPktOUkdMBVkLyNyQH1AqS6f1Ez39N4UiVAJE04beS/FeSF5CcSLLNc46hJA8heb4Y880pzLVMeI3kob3KBBvlOoRZ7FmmljDTa7lAG7mqzxeSfNGzuhj47nckP09yVOQ+TOB/7STnipTTI1z6XK+SHK+g9qYSvuR810pyihgnbcjsxf13XuJ79Pw0kg850ueDMyyBdpC8huRwZxWVlLo0IdfWYfpgiWk6AkwvK+xpaNO8I+eiWkmeIG7Z8xFjRpLH+xiX8TzjSN6eU88vJnlwvW6uRwgmS4BGD25lPy9uuCrSHBU4+fMkn0rxsa0kvkRyoIIPsrqVVuq2e2KIkFeyiuTHGxVf+BhBch+Sy1I8vbMbxgRHGj8tOtVFMCsBlJIkv58GB3uyZGeRfDqHnn+Z5BzFvKbABcrV3ovkw57rsCrwVXEU6lNFiuvvJ/nLFAg4xIDZMQZoQpE8iuQDOfR8B8lvOHBGMYtEN4AJ+4owuivT3veCulaBIv7J4sIxEpzEQv7JoQtRam0kyZvVccoZ3Mp7SE5yrzeHK2tqJY6izVQVTScOPd4gObImr0idYG5EDSSRqDJRqcH3+i5CeSJjlFsZOqbW8/9LclYePa9ti1UhrudTBxO+6aGPvd75ubNx6sCXRqRRf95B8jEP4kkB5Ib7lr06z3eVOonp+U0kLyE5wEfUjF7MLJIPCgS+nOQpvtWRB4cSo/wHx/22weczJFsyH1fpt9kRlVNW/7uZ5IEe/CdRRBsaYIA1mA+pZexWRthj3kRydE49rwk/ieQvAqv1P0kenkeVeYToWs9KtUI6JdM1K+IfrWDYEPFXWt2uJKtWBjwY2Jck7yN5ZE51o72pfcVIdziMdYG53aJKRuZkslWj4yUHkTh5b5L8aipjVQQ4lORzKSH3QgumSTBWkECrVgYs8wRYG0iekUc9aMhC3s8R99QF1ZKImntF7F4ph5qz97HcOZ59XZpqiNWFL0yJ8ua7OJB8bgQDrATdT3JQHXr+GFmhrstcSXEo9D2vITkzy8pTzLrSoVWiMKK9gu6vIuLhHpdKH/Aa92IazACrJhba1ZUzSDyY5F0eiXfrhJIcru7dFmqOuNKWBscFaFCxsIgrTAVVNQAA/6S+M6rCoATg34wx84XblQaXaLhS0SrMqqT581Ly0iZ6dg2AM6UUpaLusQTgeQCzpYriIwCWSeVEQao1qK6lKMdIAJwKYA3J60gOl/O58YPd93lVXkM5ViLnGOm9V8W9IwM4foXkRhVWFwL7H1+nF6RXwC0ho+WBps9TNotOepEk3yT51QD2f74DIqbBHS/abJ6GO5Q2aJfgix40+CTvClIEvM2j++3OZ0UI0isM8Oj5qSSXpkAWd5E8yHOtOhpuE8h6R0piR9NlOclp6rgtcn1tKoHjMuCMoCck0r0tsOOaWMjeGwxwJH4MyVsD6cJE3MmHSc5IM6Ae+7E4J+R9O8lx6hgjJCDz0fG0GANOjeRwz04B0prJgAHqN4Ok/n9rgBjWvVypPI6WtKDKs7I+LpB2GhiYqOqIK0gOlOKwjgADZgRjC4lmk4D7NDiGHjaJAd9zpPOT4r24ej5xgED7eYNVmzXGEEWSf+eJIWL24Tckrwq4tyT5wZANMCQfdQywZcQdaRFhkxjwHeUYLPH48yFiuJL6X060XmsUvStH4t+Hh+1QqKhx3dB2dBW1uhe3VHborcove54RJL8GYAWAGeJS6qrqIoAnARwHYCaAJ9BV9FtWbuixAFYIjrS/MaZsjGFMoGwxrhQWbzbGXArgSAD3yrljbmvFoZX9ze8AbJLj0+X45ICxocVgenEFhCTbRUTnWURU2YpLnJoed7/XakRS9Yo4keQTAYg8lpC6I2aAZzkES1Sv1ei07FETGVB21E3Fh4g6BNpfflOORMKPkzyh1lyCYF/z5L5iySh9P6e6RcT64Oc6+j9REjO0lxiw3LOvJtr9MUTU48kcKfo/Zjt+Xks2Tb0fTfI7TgaPgZzJObEVcGGAARsVINbbDLDbU3kQUY/KOF2VkITyyf9CckRWCNrD7CmqJrUcSNW+parmCllXwKY+WAHW595Kcr7y51P1dURlDCL5ZcnM+QrGdINI5ooKp0ylleSiABMqCl4f1EOIpLDKZwM6QrncJjLADcRqTpp7IIdFHqjYtQ8rSH4sr9uqznF1CpR/g7vKCgBeUciddasIoBXA+wLuaS+UnbIIoKR7tHL7tNV9SwEmGnQ19FkX8mgAD5D8McmDanBbrwSwQNDXsvpZUY4/l+ShgqgWLQNeArDN8VvtTf9Fg+IAUyPxGgF502GiPeZGAM8qSBoq3jgLwKMi0UMVBF0IXCsBVIQJXwTwC2FCxbn/AoBr9XUUAGxGtSMQnhv+qBw8KyEY+K5TON4fWnlsQPcUgMMAXIdqd2TRyYEMBnAFgMdInmuMoTEmCa0GoVMiAnuhaBajzmeDtRkkJ9tjFWTHR9DVq2t/DAAfJTnMSkAG4hvPd60A2q1E96PGtoHGmB3GmMsAHAHgpyrStYwqo9rOejvJ/yE5RWgRWgkJgKIxZguAf5Bj0WG+AXCR3cUe6AF0NTPbJVMBsA+Akx2mhKR+Lbr6gMvqWG0AHiZ5kVxcpZ+0eSaiVgYYYzYYY04XWGO1UksldPUYT7P3IdIbYkJZhOzHAB5X+l/TcJZk18rW4g1zYF7tPj2pWvtNSlXA36eAY6sdnH6AEMH1ghblriZLr9tZ5JxjmVNcpZHQiyQO8pWYdJI8IOYdqnOeE4H5TwGAghiO7WI44ORSKwAmAjhPVEhI/yUkC8aYmwBMAfCrADh2BIAlJH9CcoIxZreowD5dDcaYRHkmiTFmIYAPA9ihVnlJ5ccnpjgXlob3io0tKk1hbeoxcHTUQnlfcLyXBMACqT6O6j+SRWPMCmPMdADniJdRcvRqAuA0AKulx2sIgI7+YBREyGzssQnV6Vwmg63rYZCFFm8A+KVHsA2AySSNHaRRNMasAbBESb5mUDuAH1hpDakia6CkWuFOAIejOpvhTbUirE4dBOALoicPdqo0+nKzbmtLgNBZPTnb/vSrwP5jAbTramED4DJFfCrDUQbwCZLfEMNRjDAhURLwpkwnORzAnQo7h1JL4wDs795cA93WWqNpNoCRlFyFNsD2noYBOKCgll7BGPMEgG85lhsqsptH8tqsEaLFS4wxzxpjzgEwXZIsRbW6Es/N2kF+5XqhCABlq1r6KN7YCOBttfq1GhvZA0kUwGh9oDbUegK32skmOfD0ojrP30rfGD34UaPBuL0EjNvqwNzLfJ6M0wcXqnA4PkOiyh5niGd0gqXruSF3cpLkMSuRxuTHSX64DuBqH5ILpIEjlG99ys6UqBGOPsPTSFjuZQa8R9BWTXj7emHMhz07sApcv/YW6xdnwdM9iY0PkPxZSj3n/SSPypmQuS9QWtLbDBgsFde+FXCelwGyhD8ZyfS4tTFbSP6jakWtpaL5E9JlE8piVSQDFUtJjpaUZCWQ1uwLBoxi14AoF/KfFVsBd2ZMPOubW5u35cfR1y3sOfUqlJRvdSJqnadlZCpKbzHA2rwjPOUq9vPkGFHWRZo00mon/4PkYXXkW0eRvFEd06eWnmB1RM1MT6WCu3Kuk+ibqsan2QwoySq/INAzsJXkfqFlM9KzbNz35ZT+Xdvys18d+dYjnMKsWBelj0lLVGnNwhAW1OQV8COHAZY+j5I0rp62n0dLpEpPodEVgnwWFWqq97eRdAuAiwE8LuBWKQ0JFcy9bL0ZY8waY8xMVGv+13uwdarIGgrB3ADgdGPMTGPMI0KMlt4KAFTfwmCL+TgBKAGs9hVpWa7NCOR33xa/tlV8620RqXTV0uosFcueZdyikusrPHU4ZWdZf9Fpb7KFWN/trRWg7OiZETT01NiOpwUYsJnkPur3B7I6KSXNPugL+AnJP4+pJY8qmsHqFK7d7Dn10G7fJznGI0ylPmCAPffqAB23UY3QycK5bsVaQqAWtd9HVKtplvkOb0lf7TA3gHKM8UFOz5dvZS2lzIYOxAi9yoAU6bfXfZt3f0WEkwIM2G6LmFRbqybY7JwtPy+QvMBzE20kvyLtRVra9b7P6UAmZFt6kwEquTNcEjoVT8tXuOZWMeCvAsVaZdvy48xdKDoXnrflZ5msohbp24r1fO3QPV9ptUPKHVzUTAY4hVo/i+j+JcFsmgqIDvYQ334+NrL89AX9GasD8tLc1rLTQhqr57yL3adgZYE9WuX1xmYxwCH+NZ4ANlFCdFjw2h38wkXw/tiozcjoMY8BPZbkIyn2wTfwSN/ASpLH5PSg3PLE++S8DQ3EnNV/eUpl3LdTBUdd9NJA2/2DsYR0AIIuSsJ+Y0qnuivxuadgpRToJo2CIuT+WhWEclNKbehz4sLHJ2hFlpLF6jtIjmXGGTsOMdrZ/dEl7uCMmqdgZUBEkyyClJEBs5zzrIwIlZ3Ae1Qmtamk9kMeLCj79I8AY+X9oayO/PVtNU3BUu9DTRpurPJQHQyYLjHQzR4N4XM0zs9qs7Q0tbA6bMjXhbg51DmfU0pPEg/oJVF5s+rQ87ZNaVOKG2yN8M0+BjsJo20BPOwx5eX5AEutSuflrnFSamh+pHv++lqLp9hzfNig0P8yMvIEVseYxXq3tBf2ojR8G88KsAwdo1RlEoHiQxlDSjVgfhqpixglsw8qTjLB+uZT6qlgYw0D9NhzCtY9OVzdiqgNb8uoo4L/MkL8CuMPINpC8sS6qvvUhSzwcNZewAsqMq6nesHk1PMjSH6d3adgpQV7D5A82hWySOD2qYwJKV/6dHzdpZUKahguMUFo4NHDqnqh4ZXP7DkF6zMqyZ0F7ng6T9d8BMf3Eb3iwCqfyhMk5lkFZ6cEGA9alJRNGBUsnz8mcHTWGQ6vywyHwXlsiwrc/i9F/+vofZ4DjRQaKYGWCYtTmLAh71iAjIQ/SFqGYno+bYpJMavzIec/JaUg4VmZZ3Gc0zDe+N4Hdh/mtz7AhLLKt/5R6tSSL/kiQDl2aFz8MA8immWOz1/XKgRK2JYFCsZeZ3Wi5AAf45qZYrNe0XiFEYVCbrL6rMi5JNsjTA31GoxidWBsngc0vKiLnGppAFHEnxkIQBN2jaXv8eCK3shzFlUU+1pgJbiqYLOoj9lSgNUWwP4nSvXAYtUokiXxv1NK3PfO48qG8CNWZ/487Ul72vfTgiMHepkJE9g1Wr4zA8ysB2bYh+Y8IiptU6TCIcbc1GmGOe7L5p1viuD4v264ga2TCfuSvDfFK8n72Kgyw4+fstsaksc1Sv8q4s9JsW/Tm2Zoa7UJ8v6zCjMJMcIHOceemO0j/qusPqQt80TbrN6WGtcQmpd6d78hvusdyfuxUrK+25GcPE/JjoX869g1gb1Ujw72uLnzAvCCtTVbBGHte/WTASKYyOoDL1+JRI/uX9mT/nT320XyDqcKu8Qcjwdhz4d+7qfqXysexNNK/4n9TvpjcIF83ltqi24VQ9uRYQW8FQG66KihwR5QL+tjb/dSbaghF9eu5MvrxnRSNtME22CchyAXAIxBdS7d+wCMUGWPO1DtRnwZwHMAPi2lj2kPfn4ewI8A/BzAk1nGKLP6GNqTUX3w83jPMYHuD36+0RhzsZRUlvcIBjiYiu4/y7PvVQCuRFfdZ+zR50T1kef20ecvA3hDvrePPp+Arkef66EcvkefQ76/wRhzieobJvbUTRdwsfsTst2nZWvUc47TmZ6kQMBZt84McMalWVDTP9mN3Z9OtD5DnFFxDLr+64x4Ym5g99t+5ev3EyYMcRr5mNO1ZYRhVADi9apOtYR3N+8zg29VnpILeVQiEXQlAG3sZHVi/KSmwsl7OBPcIquxUv+/MqNr66uIWEXyMjdf0Ff63uwhjPC5txMBTEV1ztsE8XjaAAwUL2gXgO3iGa0HsArAcmPMWkfiKYOW+mT7f7K3dfniqVdrAAAAAElFTkSuQmCC">3. Reviewer<span class="pill p-green">Sandbox /<br>Antilaundering</span></div>
    </div>
    <div class="navlbl">Vistas del sistema</div>
    <nav id="views">
      <a data-v="preview"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/></svg>Vista previa<span class="pill p-grey">Alcance</span></a>
      <a data-v="tests"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M8 15h8"/></svg>Configuración de pruebas<span class="pill p-grey">Perfil</span></a>
      <a data-v="monitor"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h4l3-7 4 14 3-7h4"/></svg>Monitor en Vivo<span class="pill p-grey">Live</span></a>
      <a data-v="exec" class="off"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/></svg>Ejecución de Pruebas<span class="pill p-grey">PyTest CI</span></a>
      <a data-v="report" class="off"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h7"/></svg>Reporte Final<span class="pill p-grey">Auditoría</span></a>
      <a data-v="history"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 5-6"/></svg>Historial<span class="pill p-grey">Corridas</span></a>
    </nav>
  </div>

  <div class="sidefoot">
    <div class="runner">
      <div class="row" id="sbRow"><b>Sandbox Runner:</b><span id="sbEstado" class="ok"><span id="sbDot" class="dot"></span><span id="sbTxt">pyagent-sandbox:base</span></span></div>
      <div class="row sbhelp" id="sbAyuda" style="display:none"><span id="sbAyudaTxt" class="no">Abre Docker Desktop</span><button type="button" onclick="actualizarSandbox()">Reintentar</button></div>
      <div class="row"><span>Reintentos max:</span><span>3 por test</span></div>
    </div>
    <div class="sidebottom"><span>☾ Tema Oscuro</span><span class="mono">⑂ <span id="branchLbl">main</span></span></div>
  </div>
</aside>
`);

/* Indicador de estado del sandbox: consulta a Python al abrir y cada 15 s */
const SANDBOX_UI = {
  ok:           {dot:'dot',       txt:'ok',   label:'pyagent-sandbox:base',          ayuda:''},
  sin_imagen:   {dot:'dot amber', txt:'warn', label:'Falta imagen base',     ayuda:''},
  no_iniciado:  {dot:'dot red',   txt:'no',   label:'Sandbox no disponible', ayuda:'Abre Docker Desktop'},
  no_instalado: {dot:'dot red',   txt:'no',   label:'Sandbox no disponible', ayuda:'Instala Docker Desktop'},
};
let sandboxConsultando = false;
async function actualizarSandbox() {
  // Sin pywebview (HTML abierto en el navegador) se mantiene el estado verde del demo
  if (!(window.pywebview && window.pywebview.api && window.pywebview.api.estado_sandbox)) return;
  if (sandboxConsultando) return;
  sandboxConsultando = true;
  try {
    const r = await window.pywebview.api.estado_sandbox();
    const ui = SANDBOX_UI[r && r.estado] || SANDBOX_UI.no_iniciado;
    $('sbDot').className = ui.dot;
    $('sbEstado').className = ui.txt;
    $('sbTxt').textContent = ui.label;
    $('sbRow').title = ui === SANDBOX_UI.ok ? '' : (r && r.mensaje) || '';
    $('sbAyudaTxt').textContent = ui.ayuda;
    $('sbAyuda').title = (r && r.mensaje) || '';
    $('sbAyuda').style.display = ui.ayuda ? '' : 'none';
  } catch (err) {
    console.error("Error al consultar el estado del sandbox:", err);
  } finally {
    sandboxConsultando = false;
  }
}
function iniciarEstadoSandbox() {
  actualizarSandbox();
  setInterval(actualizarSandbox, 15000);
}

// Resalta la pantalla activa y alterna el menú de inicio / el menú del proyecto. Lo invoca go(v).
function actualizarSidebar(v){
  const home = v==='welcome' || v==='config';
  $('sideHome').classList.toggle('hide', !home);
  $('sideProj').classList.toggle('hide', home);
  document.querySelectorAll('#sideHome nav a').forEach(a => a.classList.toggle('on', a.dataset.h===v));
  document.querySelectorAll('#views a').forEach(a => {
    a.classList.toggle('on', a.dataset.v===v);
    const pill = a.querySelector('.pill');
    if(pill) pill.className = a.dataset.v===v ? 'pill p-green' : 'pill p-grey';
  });
}

// Se llama desde main.js cuando el HTML de la barra lateral ya está montado.
function iniciarSidebar(){
  document.querySelectorAll('#views a').forEach(a => a.onclick = () => {
    if(a.classList.contains('off')) return;
    if(a.dataset.v==='monitor' && !monitorStarted) return;
    go(a.dataset.v);
  });
  if (window.pywebview && window.pywebview.api) iniciarEstadoSandbox();
  else window.addEventListener('pywebviewready', iniciarEstadoSandbox, {once:true});
}
