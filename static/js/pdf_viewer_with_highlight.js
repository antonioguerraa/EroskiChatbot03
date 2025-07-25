/**
# =====================================================
# static/js/pdf_viewer_with_highlight.js - Visor PDF con resaltado
# =====================================================
"""
JavaScript para el frontend que maneja el resaltado de chunks en PDFs
"""
*/

/**
 * Visor PDF con capacidad de resaltado de chunks
 */
class PDFHighlightViewer {
    constructor(containerElement, pdfUrl) {
        this.container = containerElement;
        this.pdfUrl = pdfUrl;
        this.highlights = [];
        this.currentPage = 1;
        this.pdfDoc = null;
        
        this.init();
    }
    
    async init() {
        // Cargar PDF.js
        if (typeof pdfjsLib === 'undefined') {
            await this.loadPDFJS();
        }
        
        // Configurar PDF.js
        pdfjsLib.GlobalWorkerOptions.workerSrc = 
            'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.worker.min.js';
        
        await this.loadPDF();
        this.parseURLParams();
        this.renderCurrentPage();
    }
    
    async loadPDFJS() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.11.338/pdf.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    async loadPDF() {
        try {
            this.pdfDoc = await pdfjsLib.getDocument(this.pdfUrl).promise;
            console.log('PDF cargado:', this.pdfDoc.numPages, 'páginas');
        } catch (error) {
            console.error('Error cargando PDF:', error);
        }
    }
    
    parseURLParams() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // Página específica
        if (urlParams.has('page')) {
            this.currentPage = parseInt(urlParams.get('page'));
        }
        
        // Resaltado simple
        if (urlParams.has('highlight')) {
            try {
                const highlight = JSON.parse(urlParams.get('highlight'));
                this.highlights = [highlight];
            } catch (e) {
                console.error('Error parseando highlight:', e);
            }
        }
        
        // Múltiples resaltados
        if (urlParams.has('multi_highlight')) {
            try {
                this.highlights = JSON.parse(urlParams.get('multi_highlight'));
            } catch (e) {
                console.error('Error parseando multi_highlight:', e);
            }
        }
    }
    
    async renderCurrentPage() {
        if (!this.pdfDoc) return;
        
        const page = await this.pdfDoc.getPage(this.currentPage);
        const viewport = page.getViewport({ scale: 1.5 });
        
        // Crear canvas
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        
        // Limpiar container
        this.container.innerHTML = '';
        this.container.appendChild(canvas);
        
        // Renderizar PDF
        await page.render({
            canvasContext: context,
            viewport: viewport
        }).promise;
        
        // Agregar resaltados
        this.addHighlights(viewport);
        
        // Agregar controles de navegación
        this.addNavigationControls();
    }
    
    addHighlights(viewport) {
        const highlightsContainer = document.createElement('div');
        highlightsContainer.style.position = 'absolute';
        highlightsContainer.style.top = '0';
        highlightsContainer.style.left = '0';
        highlightsContainer.style.pointerEvents = 'none';
        
        this.highlights.forEach((highlight, index) => {
            if (highlight.page === this.currentPage) {
                const highlightElement = this.createHighlightElement(highlight, viewport, index);
                highlightsContainer.appendChild(highlightElement);
            }
        });
        
        // Hacer container relativo para posicionamiento absoluto
        this.container.style.position = 'relative';
        this.container.appendChild(highlightsContainer);
    }
    
    createHighlightElement(highlight, viewport, index) {
        const element = document.createElement('div');
        
        // Convertir coordenadas PDF a coordenadas del canvas
        const x = highlight.x * viewport.scale;
        const y = (viewport.height - highlight.y - highlight.height) * viewport.scale;
        const width = highlight.width * viewport.scale;
        const height = highlight.height * viewport.scale;
        
        // Estilos del resaltado
        element.style.position = 'absolute';
        element.style.left = x + 'px';
        element.style.top = y + 'px';
        element.style.width = width + 'px';
        element.style.height = height + 'px';
        element.style.backgroundColor = highlight.color || 'rgba(255, 255, 0, 0.3)';
        element.style.border = '2px solid rgba(255, 215, 0, 0.8)';
        element.style.borderRadius = '3px';
        element.style.pointerEvents = 'auto';
        element.style.cursor = 'pointer';
        
        // Tooltip con información del chunk
        if (highlight.chunk_id) {
            element.title = `Chunk: ${highlight.chunk_id}${highlight.title ? ' - ' + highlight.title : ''}`;
        }
        
        // Click handler para mostrar información
        element.addEventListener('click', () => {
            this.showChunkInfo(highlight);
        });
        
        return element;
    }
    
    showChunkInfo(highlight) {
        // Mostrar información del chunk en modal o panel lateral
        const info = `
            Chunk ID: ${highlight.chunk_id || 'N/A'}
            Coordenadas: (${highlight.x}, ${highlight.y})
            Dimensiones: ${highlight.width} x ${highlight.height}
        `;
        
        alert(info); // Reemplazar con modal más elegante
    }
    
    addNavigationControls() {
        const controls = document.createElement('div');
        controls.style.marginTop = '10px';
        controls.style.textAlign = 'center';
        
        // Botón página anterior
        const prevBtn = document.createElement('button');
        prevBtn.textContent = '← Anterior';
        prevBtn.disabled = this.currentPage <= 1;
        prevBtn.onclick = () => this.changePage(-1);
        
        // Información de página
        const pageInfo = document.createElement('span');
        pageInfo.textContent = ` Página ${this.currentPage} de ${this.pdfDoc.numPages} `;
        pageInfo.style.margin = '0 10px';
        
        // Botón página siguiente
        const nextBtn = document.createElement('button');
        nextBtn.textContent = 'Siguiente →';
        nextBtn.disabled = this.currentPage >= this.pdfDoc.numPages;
        nextBtn.onclick = () => this.changePage(1);
        
        controls.appendChild(prevBtn);
        controls.appendChild(pageInfo);
        controls.appendChild(nextBtn);
        
        this.container.appendChild(controls);
    }
    
    async changePage(delta) {
        const newPage = this.currentPage + delta;
        
        if (newPage >= 1 && newPage <= this.pdfDoc.numPages) {
            this.currentPage = newPage;
            await this.renderCurrentPage();
            
            // Actualizar URL
            const url = new URL(window.location);
            url.searchParams.set('page', this.currentPage);
            window.history.replaceState({}, '', url);
        }
    }
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    const pdfContainer = document.getElementById('pdf-container');
    const pdfUrl = document.getAttribute('data-pdf-url');
    
    if (pdfContainer && pdfUrl) {
        new PDFHighlightViewer(pdfContainer, pdfUrl);
    }
});

